# pg-bloat-detective

Read-only Postgres bloat detective: cheap timeline, named blocker, index bloat, evidence-linked report, before/after proof.

## Quickstart

```bash
docker compose up -d
pip install -e ".[dev]"
python -m bloatdetective collect --db timeline.db   # snapshot prod (read-only)
python workload/churn.py --mode idle-xact --secs 60 &  # create the failure
python -m bloatdetective collect --db timeline.db
python -m bloatdetective report --db timeline.db
pytest
bash scripts/benchmark.sh   # full before/after proof -> REPORT.md
```

## Verdicts

`normal` (steady-state, leave alone) · `vacuum-starved` · `blocked-by-idle-xact|slot|prepared` · `needs-rewrite`

## Benchmark (measured 2026-10-05, local PG16, `bash scripts/benchmark.sh`)

45s churn + `idle-xact` blocker (pid 142, xmin held 45s) → kill blocker → `VACUUM ANALYZE`:

| moment | pg_stat dead | approx dead% | verdict |
|---|---|---|---|
| before fix | 2,311,245 | 73.5% | blocked (xmin pinned by pid 142) |
| after fix | 0 | 0.0% | normal — steady state, leave alone |

100% of dead tuples reclaimed. Full log in `REPORT.md`, visual in `report.html`.

See [PLAN.md](PLAN.md) for the detailed 3-week plan + competitor gap.
