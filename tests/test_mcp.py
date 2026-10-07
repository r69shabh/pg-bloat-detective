"""MCP tools over a seeded timeline: check/timeline/blockers return the red story + actions."""
import asyncio
import sqlite3
from bloatdetective.mcp_server import mcp


def _seed(db):
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL); CREATE TABLE index_stats(ts INT, idx TEXT, tbl TEXT, scans INT, size_bytes INT); CREATE TABLE settings(ts INT, name TEXT, setting TEXT);")
    con.execute("INSERT INTO snapshots VALUES (1,'table','churn',200000,1000,0,0,'','')")
    con.execute("INSERT INTO snapshots VALUES (2,'table','churn',200000,2630921,0,0,'','')")
    con.execute("INSERT INTO blockers VALUES (1,'active',43,'0:00:52','SELECT pg_sleep($1)','',1)")
    con.execute("INSERT INTO approx VALUES (1,'churn',82.48,NULL,NULL)")
    con.execute("INSERT INTO approx VALUES (1,NULL,NULL,'churn_pkey',39.75)")
    con.execute("INSERT INTO index_stats VALUES (1,'churn_pkey','churn',22000,100000)")
    con.execute("INSERT INTO settings VALUES (1,'autovacuum_vacuum_threshold','50')")
    con.execute("INSERT INTO settings VALUES (1,'autovacuum_vacuum_scale_factor','0.2')")
    con.commit()
    con.close()


def _call(name, args):
    return asyncio.run(mcp.call_tool(name, args))[0].text


def test_mcp_tools_listed():
    names = asyncio.run(mcp.list_tools())
    assert {t.name for t in names} >= {"bloat_check", "bloat_collect", "bloat_timeline", "bloat_blockers", "bloat_live_diagnose"}


def test_bloat_check_names_blocker_and_action(tmp_path):
    db = str(tmp_path / "m.db")
    _seed(db)
    import json
    out = json.loads(_call("bloat_check", {"db": db}))
    assert out["findings"][0]["verdict"] == "blocked-by-active-xact"
    assert "pid=43" in out["findings"][0]["evidence"]
    assert "VACUUM churn" in out["findings"][0]["action"]
    assert out["findings"][1]["verdict"] == "index-bloated"
    assert "REINDEX" in out["findings"][1]["action"]


def test_bloat_timeline_and_blockers(tmp_path):
    db = str(tmp_path / "m.db")
    _seed(db)
    import json
    tl = json.loads(_call("bloat_timeline", {"table": "churn", "db": db}))
    assert tl["churn"]["dead"][-1]["dead"] == 2630921
    assert tl["index_bloat"]["churn_pkey"][0]["bloat_pct"] == 39.75
    bl = json.loads(_call("bloat_blockers", {"db": db}))
    assert bl["blockers"][0]["pid"] == 43
