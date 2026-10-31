# Operational audit lives as JSON in R2, not a database

Each Run writes `ops/runs/<run_id>/pipeline.json`, each Source Run writes `ops/runs/<run_id>/sources/<source_id>.json`, and a small `ops/latest/<source_id>.json` pointer feeds freshness and quarantine decisions. Records are written incrementally, so a crash preserves the outcomes already recorded and freshness never depends on replaying Silver.

The rejected alternative — `ops` tables in a hosted database — would reintroduce the persistent database that ADR-0008 rules out and make bookkeeping a second failure domain. The cost is coarse querying, which is acceptable because ops is read by the pipeline and one freshness view, not by analysts.

## Consequences

- Both OJK adapters write under one logical `OJK_SPI` Source; `OpsStore` merges their status, counts, and checksums instead of letting the second write overwrite the first.
- Retention is manual and lives in object storage; there is no query planner or index over run history.
- The freshness view reads these JSON records at build time; Gold does not persist ops state.
