"""Verdicts per table: normal | vacuum-starved | blocked-by-X | needs-rewrite."""
from __future__ import annotations
import sqlite3

# autovacuum trigger: dead > 50 + 20% * live (scale_factor 0.2 default)
def trigger_threshold(live: int) -> float:
    return 50 + 0.2 * live

def analyze(db_path: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    out = []
    tables = [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots")]
    blockers = con.execute("SELECT kind, pid, query, slot FROM blockers ORDER BY ts DESC LIMIT 20").fetchall()
    blocker = blockers[0] if blockers else None
    for t in tables:
        rows = con.execute("SELECT live, dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,)).fetchall()
        if not rows:
            continue
        live, dead = rows[-1]
        grow = dead - rows[0][1] if len(rows) > 1 else 0
        approx = con.execute("SELECT dead_pct FROM approx WHERE tbl=? ORDER BY ts DESC LIMIT 1", (t,)).fetchone()
        dead_pct = approx[0] if approx else (dead / max(live + dead, 1) * 100)
        thr = trigger_threshold(live)
        if blocker and dead > thr and grow > 0:
            kind = {"idle in transaction": "blocked-by-idle-xact", "stale-slot": "blocked-by-slot",
                    "prepared-xact": "blocked-by-prepared"}.get(blocker[0], f"blocked-by-{blocker[0]}")
            verdict, evidence = kind, f"{blocker}"
        elif dead > thr and grow > 0:
            verdict, evidence = "vacuum-starved", f"dead={dead} > threshold={thr:.0f}, growing +{grow}"
        elif dead_pct > 30:
            verdict, evidence = "needs-rewrite", f"pgstattuple_approx dead={dead_pct:.1f}% — VACUUM can't reclaim, needs pg_repack/VACUUM FULL"
        else:
            # steady-state bloat: tables settle, rewrite just re-grows — leave alone
            verdict, evidence = "normal", f"dead={dead} (threshold {thr:.0f}), approx {dead_pct:.1f}% — steady state, leave alone"
        out.append({"table": t, "verdict": verdict, "evidence": evidence, "dead": dead, "live": live})
    con.close()
    return out
