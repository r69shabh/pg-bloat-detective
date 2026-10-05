"""Read-only sampler: catalog stats + blockers -> SQLite timeline."""
from __future__ import annotations
import sqlite3, time
import psycopg

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(ts INTEGER, kind TEXT, tbl TEXT, live INT, dead INT, vac_ct INT, avac_ct INT, last_vac TEXT, last_avac TEXT);
CREATE TABLE IF NOT EXISTS blockers(ts INTEGER, kind TEXT, pid INT, xact_age TEXT, query TEXT, slot TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS approx(ts INTEGER, tbl TEXT, dead_pct REAL, idx TEXT, idx_bloat_pct REAL);
CREATE TABLE IF NOT EXISTS index_stats(ts INTEGER, idx TEXT, tbl TEXT, scans INT, size_bytes INT);
CREATE TABLE IF NOT EXISTS settings(ts INTEGER, name TEXT, setting TEXT);
""";

TABLES_SQL = "SELECT relname, n_live_tup, n_dead_tup, vacuum_count, autovacuum_count, last_vacuum, last_autovacuum FROM pg_stat_user_tables"
INDEX_SQL = "SELECT indexrelname, relname, idx_scan, pg_relation_size(indexrelid) FROM pg_stat_user_indexes"
SETTINGS_SQL = "SELECT name, setting FROM pg_settings WHERE name LIKE 'autovacuum%'"
BLOCKERS_SQL = """
SELECT pid, now()-xact_start AS age, state, query, backend_xmin FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL AND pid <> pg_backend_pid() ORDER BY xact_start LIMIT 20"""
SLOTS_SQL = "SELECT slot_name, active FROM pg_replication_slots"
PREPARED_SQL = "SELECT gid FROM pg_prepared_xacts"
HAS_EXT_SQL = "SELECT count(*) FROM pg_extension WHERE extname='pgstattuple'"

# ponytail: pgstattuple_approx only on tables < cost guard (default 1GB) unless --allow-large
APPROX_SQL = "SELECT * FROM pgstattuple_approx(%s)"

def init_db(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con

def collect(dsn: str, db_path: str, approx: bool = True, max_bytes: int = 1_073_741_824) -> None:
    con = init_db(db_path)
    ts = int(time.time())
    with psycopg.connect(dsn, options="-c statement_timeout=5000 -c default_transaction_read_only=on") as pg:
        rows = pg.execute(TABLES_SQL).fetchall()
        con.executemany("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
            [(ts, "table", r[0], r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0, str(r[5]), str(r[6])) for r in rows])
        con.executemany("INSERT INTO index_stats VALUES (?,?,?,?,?)",
            [(ts, r[0], r[1], r[2] or 0, r[3] or 0) for r in pg.execute(INDEX_SQL).fetchall()])
        con.executemany("INSERT INTO settings VALUES (?,?,?)",
            [(ts, r[0], r[1]) for r in pg.execute(SETTINGS_SQL).fetchall()])
        for pid, age, state, q, xmin in pg.execute(BLOCKERS_SQL).fetchall():
            con.execute("INSERT INTO blockers VALUES (?,?,?,?,?,?,?)", (ts, state, pid, str(age), (q or "")[:500], "", 1 if xmin else 0))
        for name, active in pg.execute(SLOTS_SQL).fetchall():
            if not active:
                con.execute("INSERT INTO blockers VALUES (?,?,?,?,?,?,?)", (ts, "stale-slot", None, "", "", name, 0))
        for (gid,) in pg.execute(PREPARED_SQL).fetchall():
            con.execute("INSERT INTO blockers VALUES (?,?,?,?,?,?,?)", (ts, "prepared-xact", None, "", gid, "", 1))
        if approx and pg.execute(HAS_EXT_SQL).fetchone()[0]:
            for (t,) in pg.execute("SELECT relname FROM pg_stat_user_tables").fetchall():
                size = pg.execute("SELECT pg_relation_size(%s)", (t,)).fetchone()[0]
                if size > max_bytes:
                    continue
                try:
                    r = pg.execute(APPROX_SQL, (t,)).fetchone()
                    # (table_len, tuple_count, tuple_len, dead_count, dead_len, free_space)
                    dead_pct = (r[3] / r[1] * 100) if r[1] else 0.0
                    con.execute("INSERT INTO approx VALUES (?,?,?,NULL,NULL)", (ts, t, round(dead_pct, 2)))
                except Exception:
                    pg.rollback()  # failed approx must not poison the read tx
                    continue
    con.commit()
    con.close()
