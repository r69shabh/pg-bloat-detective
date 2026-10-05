"""Deep unit tests for the analysis engine: parsing, priority, thresholds, verdicts."""
import sqlite3
import pytest
from bloatdetective.analyze import _age_secs, pick_blocker, trigger_threshold, analyze

def test_age_secs_formats():
    assert _age_secs("00:05:00") == 300.0
    assert _age_secs("01:00:00") == 3600.0
    assert _age_secs("2 days, 03:00:00") == 2 * 86400 + 3 * 3600
    assert _age_secs("1 day, 00:00:01") == 86401.0
    assert _age_secs("") == -1.0
    assert _age_secs("garbage") == -1.0
    assert _age_secs(None or "") == -1.0

def test_pick_blocker_none_empty():
    assert pick_blocker([]) is None
    assert pick_blocker(None or []) is None

def test_pick_blocker_unknown_kind_sorts_last():
    b = pick_blocker([("weird-state", 1, "00:10:00", "q", ""), ("stale-slot", None, "", "", "s")])
    assert b[0] == "stale-slot"

def test_pick_blocker_unparseable_age_loses():
    b = pick_blocker([("idle in transaction", 1, "???", "q1", ""), ("idle in transaction", 2, "00:00:05", "q2", "")])
    assert b[1] == 2

def test_threshold_defaults():
    assert trigger_threshold(10000, {}) == 50 + 0.2 * 10000

def test_threshold_custom_settings():
    assert trigger_threshold(10000, {"autovacuum_vacuum_threshold": "100", "autovacuum_vacuum_scale_factor": "0.1"}) == 1100.0

def _db(tmp_path, snaps, blockers=(), approx=(), settings=(), name="t.db"):
    db = str(tmp_path / name)
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL); CREATE TABLE settings(ts INT, name TEXT, setting TEXT);")
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", snaps)
    con.executemany("INSERT INTO blockers VALUES (?,?,?,?,?,?,?)", blockers)
    con.executemany("INSERT INTO approx VALUES (?,?,?,?,?)", approx)
    con.executemany("INSERT INTO settings VALUES (?,?,?)", settings)
    con.commit()
    con.close()
    return db

GROWING = [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")]

def test_needs_rewrite_high_approx(tmp_path):
    db = _db(tmp_path, [(1, "table", "arch", 5000, 100, 9, 9, "", "")],
             approx=[(1, "arch", 45.0, None, None)])
    f = analyze(db)[0]
    assert f["verdict"] == "needs-rewrite"

def test_rewrite_boundary(tmp_path):
    db = _db(tmp_path, [(1, "table", "arch", 5000, 100, 9, 9, "", "")],
             approx=[(1, "arch", 30.0, None, None)])
    assert analyze(db)[0]["verdict"] == "normal"  # strictly > 30

def test_custom_threshold_from_settings(tmp_path):
    # dead=500 beats default thr 2050? no: 500 < 2050 -> normal; with scale 0.01 thr=150 -> starved
    snaps = [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 500, 0, 0, "", "")]
    db = _db(tmp_path, snaps)
    assert analyze(db)[0]["verdict"] == "normal"
    db = _db(tmp_path, snaps, settings=[(2, "autovacuum_vacuum_threshold", "50"), (2, "autovacuum_vacuum_scale_factor", "0.01")], name="t2.db")
    assert analyze(db)[0]["verdict"] == "vacuum-starved"

def test_horizon_field_present(tmp_path):
    db = _db(tmp_path, GROWING, [(2, "idle in transaction", 7, "00:02:00", "SELECT 1", "", 1)])
    f = analyze(db)[0]
    assert f["horizon"] == "00:02:00"

def test_horizon_none_without_blocker(tmp_path):
    db = _db(tmp_path, GROWING)
    assert analyze(db)[0]["horizon"] is None

def test_single_snapshot_no_growth_assumption(tmp_path):
    db = _db(tmp_path, [(1, "table", "churn", 10000, 9000, 0, 0, "", "")],
             [(1, "idle in transaction", 7, "00:02:00", "SELECT 1", "", 1)])
    # one snapshot -> grow=0 -> must NOT blame blocker
    assert analyze(db)[0]["verdict"] == "normal"

def test_missing_settings_table_tolerated(tmp_path):
    # old DBs without settings table still analyze (defaults)
    db = str(tmp_path / "t.db")
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL);")
    con.execute("INSERT INTO snapshots VALUES (1,'table','churn',10000,100,0,0,'','')")
    con.commit()
    con.close()
    assert analyze(db)[0]["verdict"] == "normal"

def test_evidence_names_slot(tmp_path):
    db = _db(tmp_path, GROWING, [(2, "stale-slot", None, "", "", "abandoned_demo", 0)])
    assert "abandoned_demo" in analyze(db)[0]["evidence"]

def test_latest_settings_win(tmp_path):
    snaps = [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 500, 0, 0, "", "")]
    db = _db(tmp_path, snaps, settings=[
        (1, "autovacuum_vacuum_scale_factor", "0.01"),   # thr=150 -> 500 starved...
        (2, "autovacuum_vacuum_scale_factor", "0.9")])   # ...but latest thr=9050 -> normal
    assert analyze(db)[0]["verdict"] == "normal"


def _idx_db(tmp_path, approx_rows=(), stats_rows=(), name="idx.db"):
    db = str(tmp_path / name)
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL); CREATE TABLE index_stats(ts INT, idx TEXT, tbl TEXT, scans INT, size_bytes INT);")
    con.execute("INSERT INTO snapshots VALUES (1,'table','churn',10000,100,0,0,'','')")
    con.executemany("INSERT INTO approx VALUES (?,?,?,?,?)", approx_rows)
    con.executemany("INSERT INTO index_stats VALUES (?,?,?,?,?)", stats_rows)
    con.commit()
    con.close()
    return db


def test_index_bloated_over_threshold(tmp_path):
    db = _idx_db(tmp_path, [(1, None, None, "churn_pkey", 83.7)],
                 [(1, "churn_pkey", "churn", 5000, 32120832)])
    f = [x for x in analyze(db) if x["table"] == "churn_pkey"][0]
    assert f["verdict"] == "index-bloated" and "83.7%" in f["evidence"]


def test_index_healthy_stays_quiet(tmp_path):
    db = _idx_db(tmp_path, [(1, None, None, "churn_pkey", 9.9)],
                 [(1, "churn_pkey", "churn", 5000, 32120832)])
    assert [x for x in analyze(db) if x["table"] == "churn_pkey"] == []


def test_index_unused_zero_scans(tmp_path):
    db = _idx_db(tmp_path, [(1, None, None, "dead_idx", 5.0)],
                 [(1, "dead_idx", "churn", 0, 8192)])
    f = [x for x in analyze(db) if x["table"] == "dead_idx"][0]
    assert f["verdict"] == "index-unused"


def test_index_null_bloat_row_ignored(tmp_path):
    # skipped-large marker (NULL bloat) + healthy scans -> no finding, no crash
    db = _idx_db(tmp_path, [(1, None, None, "big_idx", None)],
                 [(1, "big_idx", "churn", 100, 5_000_000_000)])
    assert [x for x in analyze(db) if x["table"] == "big_idx"] == []
