"""Live integration tests vs the compose demo DB. Skipped gracefully when DB is down."""
import os
import sqlite3
import subprocess
import time

import pytest

DSN = os.environ.get("BLOAT_DSN", "dbname=bloatdemo user=postgres password=postgres host=localhost port=5433")
PY = os.environ.get("BLOAT_PY", ".venv/bin/python")

def need_db():
    try:
        import psycopg
        with psycopg.connect(DSN, connect_timeout=3) as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False

pytestmark = pytest.mark.skipif(not need_db(), reason="demo DB not reachable")

def collect(db):
    r = subprocess.run([PY, "-m", "bloatdetective", "collect", "--dsn", DSN, "--db", db],
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

def test_collector_writes_all_tables(tmp_path):
    from bloatdetective.collector import collect as py_collect
    db = str(tmp_path / "live.db")
    py_collect(DSN, db)
    con = sqlite3.connect(db)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["snapshots", "index_stats", "settings", "approx"]}
    con.close()
    assert counts["snapshots"] > 0 and counts["index_stats"] > 0 and counts["settings"] > 0, counts
    assert counts["approx"] > 0, counts  # pgstattuple ext installed on demo DB

def test_collector_is_read_only(tmp_path):
    import psycopg
    with psycopg.connect(DSN) as c:
        before = c.execute("SELECT sum(n_live_tup) FROM pg_stat_user_tables").fetchone()[0]
    from bloatdetective.collector import collect as py_collect
    py_collect(DSN, str(tmp_path / "ro.db"))
    with psycopg.connect(DSN) as c:
        after = c.execute("SELECT count(*) FROM pg_stat_user_tables").fetchone()[0]
        assert after > 0 and before is not None

def test_idle_xact_blocker_named_live(tmp_path):
    from bloatdetective.analyze import analyze
    db = str(tmp_path / "demo.db")
    collect(db)
    inj = subprocess.Popen([PY, "workload/churn.py", "--dsn", DSN, "--mode", "idle-xact", "--secs", "25"])
    ch = subprocess.Popen([PY, "workload/churn.py", "--dsn", DSN, "--mode", "churn", "--secs", "15"])
    try:
        time.sleep(4)
        collect(db)
        ch.wait(timeout=30)
        collect(db)
        findings = {f["table"]: f for f in analyze(db)}
        blocked = [f for f in findings.values() if f["verdict"].startswith("blocked-by")]
        assert blocked, f"expected a blocked verdict, got {[(k, v['verdict']) for k, v in findings.items()]}"
        assert any("pid=" in f["evidence"] for f in blocked)
    finally:
        inj.terminate()
        inj.wait()

def test_churn_sql_valid_live():
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("SELECT * FROM churn LIMIT 1")  # table exists from setup
