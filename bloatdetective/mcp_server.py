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
    """Diagnose PostgreSQL bloat from a collected timeline.

    Read-only: only reads the local SQLite timeline file, never touches Postgres.
    Args:
        db: Path to the SQLite timeline file (default: BLOAT_DB env, 'timeline.db').
            Collect one first with bloat_collect, or pass any timeline.db path.
    Returns:
        findings: list of {table, verdict, evidence, action} — verdict is one of
        normal | vacuum-starved | blocked-by-idle-xact | blocked-by-slot |
        blocked-by-prepared | blocked-by-active-xact | needs-rewrite |
        index-bloated | index-unused. Evidence carries dead/live counts,
        pgstattuple approx %, pgstatindex %, blocker pid+query.
    """
    path = db or DB
    try:
        findings = analyze(path)
    except Exception:
        findings = []
    return {"findings": [{**f, "action": _action(f)} for f in findings]}


@mcp.tool()
def bloat_collect(dsn: str = "") -> dict:
    """Take a read-only Postgres snapshot into the timeline, then return fresh verdicts.

    Safe on prod: read-only transaction, 5s statement timeout, needs only
    pg_stat_* views + optional pgstattuple extension. No writes, no agents.
    Args:
        dsn: Postgres DSN, e.g. 'dbname=app user=readonly host=db.internal'.
            Default: BLOAT_DSN env. Never logs the password.
    Returns:
        {snapshot: 'saved', db: path, findings: [...with action per table/index]}.
    """
    collect(dsn or DSN, DB)
    return {"snapshot": "saved", "db": DB,
            "findings": [{**f, "action": _action(f)} for f in analyze(DB)]}


@mcp.tool()
def bloat_timeline(table: str = "", db: str = "") -> dict:
    """Dead-tuple + approx + index-bloat time series: when the bloat started.

    Read-only on the local timeline file.
    Args:
        table: Table name to filter (e.g. 'churn'). Empty = all tables.
        db: Path to the SQLite timeline file (default: BLOAT_DB env).
    Returns:
        {table: {dead: [{ts, live, dead}], approx_pct: [{ts, dead_pct}]},
         index_bloat: {index: [{ts, bloat_pct}]}}. Rising dead = vacuum-starved;
         spike-then-zero = was blocked, blocker left.
    """
    path = db or DB
    try:
        con = sqlite3.connect(path)
    except Exception:
        return {}
    try:
        names = [table] if table else [r[0] for r in con.execute("SELECT DISTINCT tbl FROM snapshots ORDER BY tbl")]
        out: dict = {}
        for t in names:
            try:
                out[t] = {
                    "dead": [{"ts": ts, "live": lv, "dead": d} for ts, lv, d in
                             con.execute("SELECT ts, live, dead FROM snapshots WHERE tbl=? ORDER BY ts", (t,))],
                    "approx_pct": [{"ts": ts, "dead_pct": p} for ts, p in
                                   con.execute("SELECT ts, dead_pct FROM approx WHERE tbl=? AND idx IS NULL ORDER BY ts", (t,))],
                }
            except Exception:
                out[t] = {"dead": [], "approx_pct": []}
        try:
            idx_names = [r[0] for r in con.execute("SELECT DISTINCT idx FROM approx WHERE idx IS NOT NULL ORDER BY idx")]
            if table:
                idx_names = [i for i in idx_names if table in i]
            out["index_bloat"] = {i: [{"ts": ts, "bloat_pct": p} for ts, p in
                                  con.execute("SELECT ts, idx_bloat_pct FROM approx WHERE idx=? AND idx_bloat_pct IS NOT NULL ORDER BY ts", (i,))] for i in idx_names}
        except Exception:
            out["index_bloat"] = {}
        return out
    except Exception:
        return {}
    finally:
        try:
            con.close()
        except Exception:
            pass


@mcp.tool()
def bloat_blockers(db: str = "") -> dict:
    """Who is pinning VACUUM: blocker pid + query + xmin age + slot.

    Read-only on the local timeline file. Priority: prepared-xact > stale-slot
    > idle-in-transaction. Fix: end the named session, then VACUUM the table.
    Args:
        db: Path to the SQLite timeline file (default: BLOAT_DB env).
    Returns:
        {blockers: [{ts, kind, pid, age, query, slot}] — newest first, max 20.
         Use pid with SELECT pg_terminate_backend(pid) after verification.
    """
    path = db or DB
    try:
        con = sqlite3.connect(path)
    except Exception:
        return {"blockers": []}
    try:
        rows = con.execute("SELECT ts, kind, pid, xact_age, query, slot FROM blockers ORDER BY ts DESC LIMIT 20").fetchall()
    except Exception:
        rows = []
    finally:
        try:
            con.close()
        except Exception:
            pass
    return {"blockers": [{"ts": ts, "kind": k, "pid": p, "age": a, "query": q, "slot": s}
                         for ts, k, p, a, q, s in rows]}


@mcp.tool()
def bloat_live_diagnose(dsn: str = "") -> dict:
    """One-shot live diagnosis without touching your timeline file.

    Snapshots into a throwaway temp DB, diagnoses, discards it. Read-only on
    Postgres (read-only tx, 5s timeout). Safest option for prod DSNs.
    Args:
        dsn: Postgres DSN (default: BLOAT_DSN env). Password never logged.
    Returns:
        {findings: [...with action], blockers: [...]} — same verdict set as
        bloat_check, plus the current xmin-holder evidence.
    """
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
