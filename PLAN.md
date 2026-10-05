# Postgres Bloat Detective — detailed plan

Stack: **Python + SQLite** (ships faster than Go; single `pip install -e .`). Read-only on prod. Deps: `psycopg[binary]` only.

## 0. Competitor check (done 2026-10-05)

| Tool | Bloat story | Gap vs us |
|---|---|---|
| pgstattuple / pg_bloat_check | exact but heavy full scan; cheap query misses bloat | no cheap-over-time + no blame |
| postgres-checkup | 28 snapshot reports, heap/index estimates | snapshot, no timeline/causality |
| pganalyze VACUUM Advisor (paid) | xmin-horizon graph, "blocked by xmin" insight | heuristic table estimates, **no index bloat** |
| pgmetrics | per-table bloat column in text report | snapshot, no timeline, no blocker naming |
| pgwatch | new `btree_bloat` metric (ioguix query), 2h interval + Grafana panels | metrics only, no verdict/evidence/proof |
| PgHero | "needs vacuum" flag, unused/duplicate indexes | no bloat %, no xmin/slot attribution |
| pg_squeeze | in-DB background rebuild via logical decoding, auto-threshold | remediation, not diagnosis; needs PK; no report |

**Niche holds:** open-source + read-only + cheap timeline + named blocker (PID/query, slot, prepared xact) + index bloat + evidence-linked report + before/after proof. Nobody does all six.

## 1. Week 1 — collector + workload (days 1–7)

- [ ] `collector.py`: poll every 60s (cron/loop): `pg_stat_user_tables` (live/dead, vac counts, last vac/avac), `pg_stat_activity` (backend_xmin holders, xact age, pid, query), `pg_replication_slots` (inactive), `pg_prepared_xacts`, autovacuum settings (`SELECT * FROM pg_settings WHERE name LIKE 'autovacuum%'`), index stats `pg_stat_user_indexes`. All read-only; `SET statement_timeout=5s; SET transaction_read_only=on`.
- [ ] `pgstattuple_approx` confirmation with cost guard: `SELECT pg_relation_size()` first, skip heap >1GB (flag `--allow-large` overrides); catch missing extension gracefully.
- [ ] Index bloat v1: reuse ioguix-style estimate query (catalog stats, no scan) + `pgstatindex`-approx on small indexes only. pganalyze admits this gap — our differentiator.
  - [x] DONE 2026-10-05: exact `pgstatindex` on indexes <1GB cost guard (metric `100-avg_leaf_density`), `--allow-large`/`--max-bytes` flags; `index-bloated` (>30%) + `index-unused` (scan=0) verdicts; `pgbloat_index_bloat_pct`/`pgbloat_index_scans` metrics + Grafana panels + dashboard chart. Live proof: 83.7%→9.9% after REINDEX.
- [ ] SQLite schema: `snapshots`, `blockers`, `approx` (already scaffolded). One file = timeline.
- [ ] `workload/churn.py`: `churn` (update/delete/insert loop), `idle-xact` (BEGIN + pg_sleep holds xmin), `slot` (abandoned logical slot). `docker compose up` → demo DB ready.
- [ ] Done = `collect` twice against compose DB produces rows in all three tables.

## 2. Week 2 — analysis engine (days 8–14)

- [ ] Dead-tuple timeline per table + xmin-horizon age (`now() - backend_xmin`, oldest holder tracked).
- [ ] Vacuum frequency vs trigger: `dead > 50 + 0.2*live` (read per-table `autovacuum_vacuum_threshold/scale_factor` from `pg_settings` + storage params when set). Under-triggered + growing = `vacuum-starved`.
- [ ] Blocker attribution priority: prepared-xact > stale-slot > idle-in-xact (oldest xmin) > starved. Record pid + query + age as evidence.
- [ ] Verdicts: `normal` (steady-state: dead flat or under threshold — "leave it alone"), `vacuum-starved`, `blocked-by-{idle-xact,slot,prepared}`, `needs-rewrite` (approx dead% >30% after vacuum can run).
- [ ] Done = `tests/test_blockers.py` green: idle-xact, slot, steady-state scenarios assert the right verdict.

## 3. Week 3 — report + proof (days 15–21)

- [ ] `report.py`: Markdown table (table, verdict, dead/live, evidence string with pid/query/slot). HTML later — Markdown first. ASCII sparkline of dead-tuple timeline per table (stdlib, no matplotlib dep).
- [ ] `scripts/benchmark.sh`: run workload → collect → apply fix (kill blocker / VACUUM) → collect → print `dead before → after, % reclaimed` into `REPORT.md` + paste numbers in README.
- [ ] 60s demo: `compose up` → `churn --mode idle-xact` → `collect/analyze` names PID+query → kill session → VACUUM → `report` shows cleared.
- [ ] Done = README has real before/after numbers from a local run, not placeholders.

## Out of scope (MVP): multi-DB fleets, auto-remediation, anything writing to prod (except workload demo DB).

## Phase 2 — thin dashboard (days 22–28, only after CLI verdicts are trusted)

Goal: present the timeline, not a new app. Constraints: zero new deps, reads the same SQLite file.
- [ ] `report --html --out report.html`: findings table + inline-SVG dead-tuple sparkline per table (done, `report.render_html`) + latest blockers list. Single static file, shareable as artifact.
- [ ] Next if users ask: Prometheus exporter (`/metrics`: dead tuples, xmin age, verdict per table) + Grafana dashboard JSON — graphs with 1% of the work of a custom frontend.
- [ ] Custom web UI explicitly deferred: only if exporter + static HTML prove insufficient.
- [ ] Done = `report.html` from a real benchmark run is screenshottable for the README.

## Risks

- `pgstattuple` not installed on prod → approx degrades to catalog estimate; report must say which method each number used.
- Bloat % alone lies (steady-state tables) → `normal` verdict exists precisely for this; never recommend rewrite on % alone.
- Large-table scans → cost guard defaults skip; explicit opt-in only.
