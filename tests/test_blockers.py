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

def test_blocked_by_active_xact(tmp_path):
    # pg_sleep holder shows as active, not idle — still pins xmin (observed live)
    db = str(tmp_path / "t.db")
    seed(db, [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")],
         [(2, "active", 103, "00:00:15", "SELECT pg_sleep($1)", "", 1)])
    assert analyze(db)[0]["verdict"] == "blocked-by-active-xact"

def test_normal_steady_state(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, [(1, "table", "churn", 10000, 800, 5, 5, "", ""), (2, "table", "churn", 10000, 820, 6, 6, "", "")])
    assert analyze(db)[0]["verdict"] == "normal"

GROWING = [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")]

def test_prepared_beats_idle_xact(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, GROWING, [(2, "idle in transaction", 123, "00:05:00", "SELECT 1", "", 1),
                        (2, "prepared-xact", None, "", "gid-xyz", "", 1)])
    assert analyze(db)[0]["verdict"] == "blocked-by-prepared"

def test_oldest_xmin_wins(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, GROWING, [(2, "idle in transaction", 111, "00:01:00", "SELECT 1", "", 1),
                        (2, "idle in transaction", 222, "00:05:00", "SELECT 2", "", 1)])
    f = analyze(db)[0]
    assert f["verdict"] == "blocked-by-idle-xact" and "pid=222" in f["evidence"]

def test_vacuum_starved(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db, GROWING)
    assert analyze(db)[0]["verdict"] == "vacuum-starved"

def test_stale_stats_still_normal(tmp_path):
    db = str(tmp_path / "t.db")
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL);")
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, "table", "churn", 90000, 1500000, 0, 0, "", ""), (2, "table", "churn", 90000, 1500000, 0, 0, "", "")])
    con.execute("INSERT INTO approx VALUES (2,'churn',1.3,NULL,NULL)")
    con.commit()
    con.close()
    f = analyze(db)[0]
    assert f["verdict"] == "normal" and "stale" in f["evidence"]
