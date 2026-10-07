# pg-bloat-detective

mcp-name: io.github.r69shabh/pg-bloat-detective

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

## MCP server (Claude Desktop / Cursor / any MCP client)

5 tools, read-only on Postgres (5s statement timeout, read-only tx). `bloat_check`
returns verdict + evidence + fix per table/index; `bloat_live_diagnose` snapshots a
throwaway DB so your timeline file is never touched — safest for prod DSNs.

```bash
pip install -e .   # pulls mcp + psycopg
bloat-mcp          # stdio transport
```

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{"mcpServers": {"bloat-detective": {
  "command": "/abs/path/pg-bloat-detective/.venv/bin/python",
  "args": ["-m", "bloatdetective.mcp_server"],
  "env": {"BLOAT_DSN": "dbname=bloatdemo user=postgres host=localhost port=5433",
          "BLOAT_DB": "/abs/path/pg-bloat-detective/timeline.db"}}}}
```

| tool | what the agent gets |
|---|---|
| `bloat_check` | verdicts + evidence + action per table/index |
| `bloat_collect` | snapshot timeline, return fresh verdicts |
| `bloat_timeline` | dead/approx/index-bloat series — when it started |
| `bloat_blockers` | pid + query + xmin age + slot — who to kill |
| `bloat_live_diagnose` | one-shot throwaway snapshot, diagnose, discard |

Public listing: [mcp.so](https://mcp.so) + [PulseMCP](https://www.pulsemcp.com) accept
GitHub submissions (server.json + README badge) — repo is ready, submit the URL after push.
