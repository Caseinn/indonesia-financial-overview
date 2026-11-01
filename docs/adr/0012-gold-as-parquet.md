# Gold is Parquet in R2

Gold is a projection of Silver: every Run folds the current revisions into facts and dimensions, renders the published views in pandas, and writes the tables as Parquet under `gold/` in the private bucket with a manifest. The JSON snapshot is a separate, denormalized copy for the dashboard (ADR-0010). Silver remains the only source of truth.

The rejected alternative was reading the Gold Parquet back as a cache to make Gold incremental: it would create a second authoritative store and force invalidation on every Silver revision, quarantine, and config change (ADR-0008).

## Consequences

- Gold has no database to host or migrate; schema changes are edits to the PyArrow schemas in `pipeline/storage/gold.py`.
- The views are plain pandas functions, so tests guard against semantic drift; the view set stays intentionally small.
- Gold Parquet is derived and disposable: a Run regenerates it from Silver, and a failed Gold write is logged and alerted without failing the Run.
- The JSON snapshot stays the dashboard contract; Gold Parquet is for inspection and query, not for the browser.
