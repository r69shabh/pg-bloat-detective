"""Verdicts per table: normal | vacuum-starved | blocked-by-X | needs-rewrite.

Plus per index: index-bloated | index-unused (only actionable index findings are
emitted; healthy indexes stay quiet so the report doesn't double in size).
Index bloat metric = 100 - pgstatindex.avg_leaf_density, same >30% rewrite
threshold as the heap path. Unused = zero idx_scan across every snapshot.
"""
from __future__ import annotations
import sqlite3

PRIORITY = {"prepared-xact": 0, "stale-slot": 1, "idle in transaction": 2, "active": 2}
VERDICTS = {"prepared-xact": "blocked-by-prepared", "stale-slot": "blocked-by-slot",
            "idle in transaction": "blocked-by-idle-xact", "active": "blocked-by-active-xact"}

def _age_secs(s: str) -> float:
    """Parse PG interval 'H:MM:SS' / 'D days, H:MM:SS' -> seconds. Unparseable = -1 (sorts last)."""
    try:
        days = 0
        if "day" in s:
            d, s = s.split("day")
            days = int(d.strip().split()[-1])
            s = s.lstrip("s").strip(", ")
        h, m, sec = s.split(":")
        return days * 86400 + int(h) * 3600 + int(m) * 60 + float(sec)
    except Exception:
        return -1.0

def _settings(con: sqlite3.Connection) -> dict:
    try:
        rows = con.execute("SELECT name, setting FROM settings ORDER BY ts ASC").fetchall()
    except Exception:
        return {}
    return dict(rows)  # ASC + dict: latest snapshot wins per setting

def trigger_threshold(live: int, s: dict) -> float:
    base = float(s.get("autovacuum_vacuum_threshold", 50))
    scale = float(s.get("autovacuum_vacuum_scale_factor", 0.2))
    return base + scale * live

def pick_blocker(blockers: list[tuple]):
    """Priority: prepared > stale slot > idle-in-xact; oldest xmin (largest age) wins within kind."""
    if not blockers:
        return None
    return sorted(blockers, key=lambda b: (PRIORITY.get(b[0], 9), -_age_secs(b[2] or "")))[0]

def analyze(db_path: str) -> list[dict]:
    try:
        con = sqlite3.connect(db_path)
    except Exception:
        return []
    try:
        s = _settings(con)
        out = []
        try:
            tables = [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots")]
        except Exception:
            return []
        try:
            blockers = con.execute("SELECT kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 50").fetchall()
        except Exception:
            blockers = []
        blocker = pick_blocker(blockers)
        for t in tables:
            rows = con.execute("SELECT live, dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,)).fetchall()
            if not rows:
                continue
            live, dead = rows[-1]
            grow = dead - rows[0][1] if len(rows) > 1 else 0
            try:
                approx = con.execute("SELECT dead_pct FROM approx WHERE tbl=? AND idx IS NULL ORDER BY ts DESC LIMIT 1", (t,)).fetchone()
            except Exception:
                approx = None
            stat_pct = dead / max(live + dead, 1) * 100
            has_approx = approx is not None
            dead_pct = approx[0] if has_approx else stat_pct
            thr = trigger_threshold(live, s)
            if blocker and dead > thr and grow > 0:
                verdict = VERDICTS.get(blocker[0], f"blocked-by-{blocker[0]}")
                who = f"pid={blocker[1]} q={blocker[3]}" if blocker[1] else f"slot={blocker[4] or blocker[3]}"
                evidence = f"xmin horizon {blocker[2]} held by {who} — vacuum cannot advance past it"
            elif dead > thr and grow > 0:
                verdict, evidence = "vacuum-starved", f"dead={dead} > threshold={thr:.0f}, growing +{grow}, no blocker — autovacuum not keeping up"
            elif has_approx and dead_pct > 30:
                # rewrite only on measured approx, never on stat % alone (single snapshot proves nothing)
                verdict, evidence = "needs-rewrite", f"pgstattuple_approx dead={dead_pct:.1f}% — VACUUM can't reclaim, needs pg_repack/VACUUM FULL"
            elif stat_pct > 20 and dead_pct < 5:
                # observed live: pg_stat counters lag (flush interval) while approx shows clean heap
                verdict, evidence = "normal", f"pg_stat dead={stat_pct:.0f}% looks stale (approx {dead_pct:.1f}%) — steady state, leave alone"
            else:
                # steady-state bloat: tables settle, rewrite just re-grows — leave alone
                verdict, evidence = "normal", f"dead={dead} (threshold {thr:.0f}), approx {dead_pct:.1f}% — steady state, leave alone"
            out.append({"table": t, "verdict": verdict, "evidence": evidence, "dead": dead, "live": live,
                        "horizon": blocker[2] if blocker else None})
        try:
            idx_rows = _index_latest(con)
        except Exception:
            idx_rows = []
        for idx, tbl, scans, size in idx_rows:
            try:
                bloat = _index_bloat(con, idx)
            except Exception:
                bloat = None
            if bloat is not None and bloat > 30:
                out.append({"table": idx, "verdict": "index-bloated",
                            "evidence": f"pgstatindex bloat={bloat:.1f}% on {tbl} — REINDEX can't be done by VACUUM, needs REINDEX",
                            "dead": 0, "live": 0, "horizon": None})
            elif _index_ever_scanned(con, idx) is False:
                out.append({"table": idx, "verdict": "index-unused",
                            "evidence": f"idx_scan=0 across snapshots on {tbl} ({size} bytes) — candidate for DROP (verify with pg_stat_statements first)",
                            "dead": 0, "live": 0, "horizon": None})
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass


def _index_latest(con: sqlite3.Connection) -> list[tuple]:
    """Latest (scans, size) per index from index_stats; tolerates old DBs."""
    try:
        return list(con.execute(
            "SELECT idx, tbl, scans, size_bytes FROM index_stats "
            "WHERE (idx, ts) IN (SELECT idx, max(ts) FROM index_stats GROUP BY idx)"))
    except Exception:
        return []


def _index_bloat(con: sqlite3.Connection, idx: str) -> float | None:
    """Latest pgstatindex bloat% for idx, or None (no measurement / skipped-large)."""
    try:
        row = con.execute("SELECT idx_bloat_pct FROM approx WHERE idx=? ORDER BY ts DESC LIMIT 1",
                          (idx,)).fetchone()
    except Exception:
        return None
    return row[0] if row else None


def _index_ever_scanned(con: sqlite3.Connection, idx: str) -> bool:
    """True if the index was ever scanned in any snapshot (cumulative counter)."""
    try:
        row = con.execute("SELECT max(scans) FROM index_stats WHERE idx=?", (idx,)).fetchone()
    except Exception:
        return True  # unknown -> don't accuse
    return (row[0] or 0) > 0
