"""Verdicts per table: normal | vacuum-starved | blocked-by-X | needs-rewrite."""
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
            s = s.strip(", ")
        h, m, sec = s.split(":")
        return days * 86400 + int(h) * 3600 + int(m) * 60 + float(sec)
    except Exception:
        return -1.0

def _settings(con: sqlite3.Connection) -> dict:
    try:
        rows = con.execute("SELECT name, setting FROM settings ORDER BY ts DESC LIMIT 50").fetchall()
    except Exception:
        return {}
    return {k: v for k, v in rows}  # latest snapshot wins; table is append-only per ts

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
    con = sqlite3.connect(db_path)
    s = _settings(con)
    out = []
    tables = [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots")]
    blockers = con.execute("SELECT kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 50").fetchall()
    blocker = pick_blocker(blockers)
    for t in tables:
        rows = con.execute("SELECT live, dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,)).fetchall()
        if not rows:
            continue
        live, dead = rows[-1]
        grow = dead - rows[0][1] if len(rows) > 1 else 0
        approx = con.execute("SELECT dead_pct FROM approx WHERE tbl=? ORDER BY ts DESC LIMIT 1", (t,)).fetchone()
        stat_pct = dead / max(live + dead, 1) * 100
        dead_pct = approx[0] if approx else stat_pct
        thr = trigger_threshold(live, s)
        if blocker and dead > thr and grow > 0:
            verdict = VERDICTS.get(blocker[0], f"blocked-by-{blocker[0]}")
            who = f"pid={blocker[1]} q={blocker[3]}" if blocker[1] else f"slot={blocker[4] or blocker[3]}"
            evidence = f"xmin horizon {blocker[2]} held by {who} — vacuum cannot advance past it"
        elif dead > thr and grow > 0:
            verdict, evidence = "vacuum-starved", f"dead={dead} > threshold={thr:.0f}, growing +{grow}, no blocker — autovacuum not keeping up"
        elif dead_pct > 30:
            verdict, evidence = "needs-rewrite", f"pgstattuple_approx dead={dead_pct:.1f}% — VACUUM can't reclaim, needs pg_repack/VACUUM FULL"
        elif stat_pct > 20 and dead_pct < 5:
            # observed live: pg_stat counters lag (flush interval) while approx shows clean heap
            verdict, evidence = "normal", f"pg_stat dead={stat_pct:.0f}% looks stale (approx {dead_pct:.1f}%) — steady state, leave alone"
        else:
            # steady-state bloat: tables settle, rewrite just re-grows — leave alone
            verdict, evidence = "normal", f"dead={dead} (threshold {thr:.0f}), approx {dead_pct:.1f}% — steady state, leave alone"
        out.append({"table": t, "verdict": verdict, "evidence": evidence, "dead": dead, "live": live,
                    "horizon": blocker[2] if blocker else None})
    con.close()
    return out
