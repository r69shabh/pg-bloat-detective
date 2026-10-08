# pg-bloat-detective — PostgreSQL Bloat Checker, Vacuum Blocker Finder & Index Bloat Detector

> **Find why your Postgres database is bloated, who is blocking VACUUM, and which indexes need REINDEX — read-only, with proof.**
> `vacuum-starved` · `blocked-by-idle-xact` · `needs-rewrite` · `index-bloated` · `index-unused` — one verdict per table/index, with PID + query evidence.

mcp-name: io.github.r69shabh/pg-bloat-detective

[![PyPI](https://img.shields.io/pypi/v/pg-bloat-detective)](https://pypi.org/project/pg-bloat-detective/)
[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-io.github.r69shabh%2Fpg--bloat--detective-blue)](https://registry.modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-48%20passed-brightgreen)](tests/)

**pip install pg-bloat-detective · Docker ready · MCP server for Claude/Cursor · Prometheus + Grafana · Next.js dashboard**

```bash
pip install pg-bloat-detective          # or: pip install -e ".[dev]" from source
python -m bloatdetective collect --db timeline.db   # read-only snapshot (5s timeout)
python -m bloatdetective analyze --db timeline.db   # verdicts + evidence
python -m bloatdetective report --db timeline.db --html --out report.html
bloat-mcp                              # MCP server (stdio) for Claude Desktop / Cursor
```

## What this is

A **PostgreSQL bloat analysis tool** that answers three questions other tools leave open:

1. **Is this table bloated, and why?** — dead-tuple timeline (`pg_stat_user_tables`) + exact `pgstattuple_approx` confirmation. Verdicts: `normal` (leave it alone), `vacuum-starved` (autovacuum losing), `blocked-by-idle-xact|slot|prepared|active-xact` (named PID + query holding `backend_xmin`), `needs-rewrite` (approx dead% >30%, VACUUM can't reclaim).

2. **Who is blocking VACUUM / autovacuum?** — oldest `backend_xmin` holder tracked per snapshot: PID, transaction age, query text, stale replication slots, prepared transactions. Priority: prepared-xact > stale-slot > idle-in-transaction. Kill one, VACUUM, done.
3. **Is the *index* bloated? (VACUUM never fixes this)** — exact `pgstatindex` on indexes under a 1GB cost guard (tunable `--max-bytes`, override `--allow-large`), metric `100 − avg_leaf_density`. Over 30% → `index-bloated`, schedule `REINDEX`. Zero scans across all snapshots → `index-unused`, DROP candidate. This is the gap pganalyze admits to — our differentiator, proven live: 83.7% → 9.9% after REINDEX while VACUUM did nothing.

One SQLite file = full timeline. One static page = the whole incident. No agents on prod, no writes (read-only transactions, statement timeout 5s), works on RDS / Neon / Supabase / self-hosted PG 12–17.

## Quickstart (60-second demo)

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

## Verdicts (read them as instructions)

Heap: `normal` (steady-state, leave alone) · `vacuum-starved` → run VACUUM / tune autovacuum · `blocked-by-idle-xact|slot|prepared|active-xact` → end the named session, then VACUUM · `needs-rewrite` → pg_repack / VACUUM FULL.
Index: `index-bloated` (pgstatindex bloat >30% → needs REINDEX, VACUUM can't fix it) · `index-unused` (idx_scan=0 across snapshots → DROP candidate, verify with pg_stat_statements first).

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
pip install pg-bloat-detective   # pulls mcp + psycopg
bloat-mcp                        # stdio transport (also: docker run -i pg-bloat-detective)
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

Public listing: official MCP Registry (`io.github.r69shabh/pg-bloat-detective`) · [mcp.so](https://mcp.so) · awesome-mcp-servers (Databases).

## Interfaces

- **CLI** — `collect | analyze | report [--html|--json] | serve [--port]` (this README's quickstart).
- **Dashboard** — Next.js single-incident card at `dashboard/` (`report --json` feeds `data.json`): verdict banner, dead-tuple + index-bloat charts, blockers + findings tables.
- **Prometheus + Grafana** — `serve` exposes `:9187/metrics` (`pgbloat_dead_tuples`, `pgbloat_approx_dead_pct`, `pgbloat_index_bloat_pct`, `pgbloat_index_scans`, `pgbloat_xmin_holder_age_seconds`); `grafana/` has dashboard JSON + provisioning, `docker-compose.yml` wires pg → exporter → Prometheus → Grafana.
- **Docker** — `Dockerfile` runs the MCP server over stdio (`docker run -i`); compose adds the demo DB + observability stack.

## FAQ (how people actually search for this)

- **"postgres table bloated how to check"** → `collect` twice, `analyze` prints the verdict + dead/live + evidence. `needs-rewrite` means pg_repack/VACUUM FULL; anything else tells you the cheaper fix first.
- **"postgres autovacuum not keeping up / dead tuples growing"** → `vacuum-starved` (threshold `50 + 0.2×live` from your live `pg_settings`) vs `blocked-by-*` (a session pinning xmin). The timeline chart shows whether dead is rising (losing) or spiked-then-zero (blocked-then-freed).
- **"postgres vacuum blocked by idle in transaction"** → we name the PID, query, and xmin age. `SELECT pg_terminate_backend(pid)` (or let it finish), then `VACUUM table`.
- **"postgres index bloat check / reindex needed"** → `index-bloated` with exact `pgstatindex` % — VACUUM cannot fix it, only REINDEX/pg_repack. Stale `pg_stat` counters are cross-checked against `pgstattuple_approx` so you don't chase ghosts.
- **"postgres unused indexes find / drop"** → `index-unused` (idx_scan=0 across every snapshot) with size in bytes. Confirm with pg_stat_statements, then DROP.
- **"rds / neon / supabase bloat"** → read-only by design; needs only `pg_stat_*` views + optional `pgstattuple` extension. No superuser, no agent install.
- **"pg_bloat_check vs pgstattuple vs pganalyze vs pghero"** → one-shot estimators give you a %; we give you the timeline + the blocker + the fix + the before/after proof, heap *and* index, in one open-source tool. See PLAN.md competitor table.

## Keywords

`postgresql bloat` · `postgres bloat check` · `pg_bloat_check alternative` · `vacuum blocked` · `autovacuum tuning` · `dead tuples` · `pgstattuple_approx` · `index bloat` · `pgstatindex` · `reindex needed` · `unused indexes` · `idle in transaction` · `backend_xmin` · `replication slot lag` · `prepared transaction` · `table bloat estimation` · `postgres dba tools` · `postgres monitoring prometheus grafana` · `MCP server postgres` · `Claude postgres DBA`
