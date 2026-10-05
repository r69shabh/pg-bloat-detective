#!/bin/bash
# Benchmark: workload -> collect -> fix -> collect -> before/after numbers.
# Usage: scripts/benchmark.sh [dsn]
set -euo pipefail
DSN="${1:-dbname=bloatdemo user=postgres password=postgres host=localhost}"
DB=timeline.db
rm -f "$DB"
python -m bloatdetective collect --dsn "$DSN" --db "$DB"
python workload/churn.py --dsn "$DSN" --mode churn --secs 60 &
python workload/churn.py --dsn "$DSN" --mode idle-xact --secs 60 &
wait || true
python -m bloatdetective collect --dsn "$DSN" --db "$DB"
echo "--- BEFORE (blocked) ---"
python -m bloatdetective report --db "$DB"
psql "$DSN" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle in transaction'; SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE NOT active;" || true
psql "$DSN" -c "VACUUM ANALYZE churn;"
python -m bloatdetective collect --dsn "$DSN" --db "$DB"
echo "--- AFTER (fixed) ---"
python -m bloatdetective report --db "$DB" | tee REPORT.md
