# pg-bloat-detective

Read-only Postgres bloat detective: cheap timeline, named blocker, index bloat, evidence-linked report, before/after proof.

## Quickstart

```bash
docker compose up -d
pip install -e ".[dev]"
python -m bloatdetective collect --db timeline.db   # snapshot prod (read-only)
python workload/churn.py --mode idle-xact --secs 60 &  # create the failure
python -m bloatdetective collect --db timeline.db
python -m bloatdetective report --db timeline.db --html --out report.html
python -m bloatdetective serve --db timeline.db &   # :9187/metrics for Prometheus
pytest
bash scripts/benchmark.sh   # full before/after proof -> REPORT.md
```

## Verdicts

Heap: `normal` (steady-state, leave alone) · `vacuum-starved` · `blocked-by-idle-xact|slot|prepared|active-xact` · `needs-rewrite`.
Index: `index-bloated` (pgstatindex bloat >30% → needs REINDEX, VACUUM can't fix it) · `index-unused` (idx_scan=0 across snapshots → DROP candidate).

Index bloat is the differentiator (pganalyze admits the gap): `collect` runs exact
`pgstatindex` only on indexes under the 1GB cost guard (`--max-bytes` tunes it,
`--allow-large` overrides), metric = `100 − avg_leaf_density`. Exported as
`pgbloat_index_bloat_pct` / `pgbloat_index_scans`, charted in the shadcn dashboard,
Graphed in Grafana.

## Benchmark (measured 2026-10-05, local PG16 — heap + index, live run just now)

30s churn, no blocker (autovacuum simply lost) → `VACUUM ANALYZE` + `REINDEX`:

| moment | pg_stat dead | approx dead% | index bloat% (density) | verdict |
|---|---|---|---|---|
| before fix | 5,108,201 | — (single-snapshot lag) | 41.9% | `vacuum-starved` + `index-bloated churn_pkey` |
| after fix | 0 | 0.0% | 9.9% | `normal` — steady state, leave alone |

Earlier hole, now closed: an index at 83.7% bloat (density 16.3) dropped to 9.9%
(density 90.1) after `REINDEX` — VACUUM alone never touches that. Full log in
`REPORT.md`, visual in `report.html`.

See [PLAN.md](PLAN.md) for the detailed 3-week plan + competitor gap.
