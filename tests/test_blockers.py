"""Failure-scenario tests: seed SQLite timelines, assert the right blocker is named."""
import sqlite3
from bloatdetective.analyze import analyze

def seed(path, snaps, blockers=()):
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL);")
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", snaps)
    con.executemany("INSERT INTO blockers VALUES (?,?,?,?,?,?,?)", blockers)
    con.commit()
    con.close()

def test_blocked_by_idle_xact(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")],
         [(2, "idle in transaction", 123, "00:05:00", "SELECT * FROM churn", "", 1)])
    assert analyze(db)[0]["verdict"] == "blocked-by-idle-xact"

def test_blocked_by_slot(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")],
         [(2, "stale-slot", None, "", "", "abandoned_demo", 0)])
    assert analyze(db)[0]["verdict"] == "blocked-by-slot"

def test_normal_steady_state(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, [(1, "table", "churn", 10000, 800, 5, 5, "", ""), (2, "table", "churn", 10000, 820, 6, 6, "", "")])
    assert analyze(db)[0]["verdict"] == "normal"
