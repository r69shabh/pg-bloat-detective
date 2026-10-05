# Bloat report

| table | verdict | dead | live | evidence |
|---|---|---|---|---|
| churn | **normal** | 0 | 191111 | dead=0 (threshold 38272), approx 0.0% — steady state, leave alone |

_Sources: pg_stat_user_tables, pg_stat_activity.backend_xmin, pg_replication_slots, pg_prepared_xacts, pgstattuple_approx._
