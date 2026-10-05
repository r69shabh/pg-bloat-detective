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

## Benchmark (fill after first run)

dead before → after: _TBD_ (run `scripts/benchmark.sh`, paste `REPORT.md` numbers here)

See [PLAN.md](PLAN.md) for the detailed 3-week plan + competitor gap.
