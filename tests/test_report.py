"""Report rendering: markdown + HTML dashboard smoke tests."""
import sqlite3
from bloatdetective.report import render, render_html, _sparkline

F = [{"table": "churn", "verdict": "blocked-by-idle-xact", "dead": 5000, "live": 10000,
      "evidence": "xmin horizon 00:05:00 held by pid=123", "horizon": "00:05:00"}]

def test_render_markdown_table():
    md = render(F)
    assert "| churn | **blocked-by-idle-xact** | 5000 | 10000 |" in md
    assert "pg_stat_activity" in md  # sources cited

def test_render_before_after():
    md = render(F, before_after=(5000, 200))
    assert "5000 → 200" in md and "96%" in md

def test_render_empty():
    assert "Bloat report" in render([])

def test_sparkline_empty():
    assert _sparkline([]) == ""

def test_sparkline_svg():
    svg = _sparkline([1, 5, 3])
    assert svg.startswith("<svg") and "polyline" in svg

def test_render_html_dashboard(tmp_path):
    db = str(tmp_path / "t.db")
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT);")
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")])
    con.execute("INSERT INTO blockers VALUES (2,'idle in transaction',123,'00:05:00','SELECT 1','',1)")
    con.commit()
    con.close()
    html = render_html(db, F)
    assert "<svg" in html and "pid=123" in html and "blocked-by-idle-xact" in html

def test_render_html_no_blockers(tmp_path):
    db = str(tmp_path / "t.db")
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT);")
    con.execute("INSERT INTO snapshots VALUES (1,'table','churn',10000,100,0,0,'','')")
    con.commit()
    con.close()
    assert "none</li>" in render_html(db, [])
