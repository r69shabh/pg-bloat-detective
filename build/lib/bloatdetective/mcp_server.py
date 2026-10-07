"""MCP server: bloat verdicts as tools. Read-only on Postgres, stdio transport.

Run:  python -m bloatdetective.mcp_server
Claude Desktop config:
  {"mcpServers": {"bloat-detective": {"command": "/abs/path/.venv/bin/python",
    "args": ["-m", "bloatdetective.mcp_server"],
    "env": {"BLOAT_DSN": "dbname=bloatdemo user=postgres host=localhost port=5433",
            "BLOAT_DB": "/abs/path/timeline.db"}}}}
"""
from __future__ import annotations
import os
import sqlite3
import tempfile
from mcp.server.fastmcp import FastMCP

from .analyze import analyze
from .collector import collect
from .report import export_json

mcp = FastMCP("bloat-detective")
DSN = os.environ.get("BLOAT_DSN", "dbname=bloatdemo user=postgres password=postgres host=localhost port=5433")
DB = os.environ.get("BLOAT_DB", "timeline.db")


def _action(f: dict) -> str:
    t, v = f["table"], f["verdict"]
    if v.startswith("blocked-by"):
        return f"End the named session, then run VACUUM {t}."
    if v == "vacuum-starved":
        return f"Run VACUUM (ANALYZE) {t} or tune autovacuum."
    if v == "needs-rewrite":
        return f"Schedule pg_repack or VACUUM FULL on {t}."
    if v == "index-bloated":
        return f"Schedule REINDEX INDEX {t} (VACUUM cannot fix index bloat)."
    if v == "index-unused":
        return f"Verify with pg_stat_statements, then DROP INDEX {t}."
    return f"No action — {t} is steady state."


@mcp.tool()
def bloat_check(db: str = "") -> dict:
    """Diagnose bloat: verdict + evidence + fix per table/index. Reads the SQLite timeline (collect first, or pass a DSN snapshot)."""
    path = db or DB
    findings = analyze(path)
    return {"findings": [{**f, "action": _action(f)} for f in findings]}


@mcp.tool()
def bloat_collect(dsn: str = "") -> dict:
    """Take a read-only snapshot (5s statement timeout, read-only tx) into the timeline, then return fresh verdicts."""
    collect(dsn or DSN, DB)
    return {"snapshot": "saved", "db": DB,
            "findings": [{**f, "action": _action(f)} for f in analyze(DB)]}


@mcp.tool()
def bloat_timeline(table: str = "", db: str = "") -> dict:
    """Dead-tuple + approx + index-bloat series for one table (or all). Shows when it started."""
    path = db or DB
    con = sqlite3.connect(path)
    names = [table] if table else [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots ORDER BY tbl")]
    out: dict = {}
    for t in names:
        out[t] = {
            "dead": [{"ts": ts, "live": lv, "dead": d} for ts, lv, d in
                     con.execute("SELECT ts, live, dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,))],
            "approx_pct": [{"ts": ts, "dead_pct": p} for ts, p in
                           con.execute("SELECT ts, dead_pct FROM approx WHERE tbl=? AND idx IS NULL ORDER BY ts", (t,))],
        }
    try:
        idx_names = [r[0] for r in con.execute("SELECT DISTINCT idx FROM approx WHERE idx IS NOT NULL ORDER BY idx")]
        if table:
            idx_names = [i for i in idx_names if table in i]
        out["index_bloat"] = {i: [{"ts": ts, "bloat_pct": p} for ts, p in
                              con.execute("SELECT ts, idx_bloat_pct FROM approx WHERE idx=? AND idx_bloat_pct IS NOT NULL ORDER BY ts", (i,))] for i in idx_names}
    except Exception:
        pass
    con.close()
    return out


@mcp.tool()
def bloat_blockers(db: str = "") -> dict:
    """Who is pinning VACUUM: pid + query + xmin age + slot. Kill one, then VACUUM."""
    path = db or DB
    con = sqlite3.connect(path)
    rows = con.execute("SELECT ts, kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 20").fetchall()
    con.close()
    return {"blockers": [{"ts": ts, "kind": k, "pid": p, "age": a, "query": q, "slot": s}
                         for ts, k, p, a, q, s in rows]}


@mcp.tool()
def bloat_live_diagnose(dsn: str = "") -> dict:
    """One-shot: snapshot throwaway DB (never touches your timeline file), diagnose, discard. Safest for prod DSNs."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        collect(dsn or DSN, tmp)
        findings = analyze(tmp)
        feed = export_json(tmp, findings)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return {"findings": [{**f, "action": _action(f)} for f in findings],
            "blockers": feed["blockers"]}


if __name__ == "__main__":
    mcp.run()
