# No hosted database; R2 plus Parquet is the only persistent store

Silver stays as Parquet objects in R2 and Gold is rebuilt from Silver on every Run and written as Parquet, so the platform has no long-lived Postgres, Supabase, or warehouse instance. The data is small, every Run is reproducible from Bronze and Silver, and no consumer needs a live SQL connection; a managed database would add cost, credentials, and a second source of truth without buying anything the free tier cannot already do.

The rejected alternative — Supabase or Postgres as the Silver/Gold store — would make the database authoritative and the Parquet export a copy. That breaks the append-only Bronze/Silver lineage, introduces connection secrets for the pipeline and the dashboard, and turns a rebuild into a migration problem.

## Consequences

- There is no public SQL endpoint and no concurrent writer; the dashboard reads pre-built snapshots instead.
- Rebuilding Gold is cheap and safe because it starts from an empty database each Run.
- Operational records also avoid the database and live as JSON in R2 (ADR-0011).
