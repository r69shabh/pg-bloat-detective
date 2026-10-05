#!/bin/bash
# Benchmark: workload -> collect (blocked) -> fix -> collect -> before/after proof.
# Usage: scripts/benchmark.sh [dsn]
set -euo pipefail
DSN="${1:-dbname=bloatdemo user=postgres password=postgres host=localhost port=5433}"
DB=timeline.db
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
rm -f "$DB" REPORT.md report.html
$PY -m bloatdetective collect --dsn "$DSN" --db "$DB"          # baseline
$PY workload/churn.py --dsn "$DSN" --mode idle-xact --secs 90 &  # blocker outlives workload
INJ=$!
$PY workload/churn.py --dsn "$DSN" --mode churn --secs 45
$PY -m bloatdetective collect --dsn "$DSN" --db "$DB"            # BEFORE: blocked, growing
echo "--- BEFORE (blocked) ---"
$PY -m bloatdetective report --db "$DB"
kill $INJ 2>/dev/null || true
wait || true
psql "$DSN" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE backend_xmin IS NOT NULL AND pid <> pg_backend_pid();" || true
psql "$DSN" -c "VACUUM ANALYZE churn;"
$PY -m bloatdetective collect --dsn "$DSN" --db "$DB"            # AFTER: fixed
echo "--- AFTER (fixed) ---"
$PY -m bloatdetective report --db "$DB" | tee REPORT.md
$PY -m bloatdetective report --db "$DB" --html --out report.html
$PY -c "
import sqlite3
con = sqlite3.connect('$DB')
rows = con.execute('SELECT dead FROM snapshots WHERE tbl=? ORDER BY ts', ('churn',)).fetchall()
b, a = rows[0][0], rows[-1][0]
print(f'dead tuples: {b} -> {a} ({(b-a)/max(b,1)*100:.0f}% reclaimed)' if len(rows) > 1 else 'need 2+ snapshots')"
