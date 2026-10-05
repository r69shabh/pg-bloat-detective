"""Exporter tests: metric format + live HTTP serve against a seeded DB."""
import sqlite3
import threading
import time
import urllib.request
from http.server import HTTPServer
from bloatdetective.exporter import collect_metrics, make_handler, serve

def seed(db):
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE snapshots(ts INT, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT); CREATE TABLE blockers(ts INT, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INT); CREATE TABLE approx(ts INT, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL); CREATE TABLE settings(ts INT, name TEXT, setting TEXT);")
    con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, "table", "churn", 10000, 100, 0, 0, "", ""), (2, "table", "churn", 10000, 5000, 0, 0, "", "")])
    con.execute("INSERT INTO blockers VALUES (2,'idle in transaction',123,'00:05:00','SELECT * FROM churn','',1)")
    con.execute("INSERT INTO approx VALUES (2,'churn',12.5,NULL,NULL)")
    con.commit()
    con.close()

def test_metrics_format(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db)
    m = collect_metrics(db)
    assert 'pgbloat_dead_tuples{table="churn",verdict="blocked-by-idle-xact"} 5000' in m
    assert 'pgbloat_live_tuples{table="churn"} 10000' in m
    assert 'pgbloat_approx_dead_pct{table="churn"} 12.5' in m
    assert 'pgbloat_xmin_holder_age_seconds{kind="idle in transaction",pid="123"' in m
    assert " 300.0" in m

def test_serve_metrics_endpoint(tmp_path):
    db = str(tmp_path / "t.db")
    seed(db)
    srv = HTTPServer(("127.0.0.1", 0), make_handler(db))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
    srv.shutdown()
    assert "pgbloat_dead_tuples" in body

def test_serve_fn_binds(tmp_path):
    # serve() itself wires the CLI path: run briefly on ephemeral port via thread
    db = str(tmp_path / "t.db")
    seed(db)
    probe = HTTPServer(("127.0.0.1", 0), object)
    port = probe.server_address[1]
    probe.server_close()
    threading.Thread(target=serve, args=(db, port), daemon=True).start()
    time.sleep(0.5)
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
    assert 'verdict="blocked-by-idle-xact"' in body
