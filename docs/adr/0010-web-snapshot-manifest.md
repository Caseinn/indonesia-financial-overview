# Web snapshots are a versioned manifest contract

`pipeline.export_web` writes one JSON file per dashboard view plus a `manifest.json` carrying `schema_version`, the producing `run_id`, `generated_at`, and the row count and SHA-256 of every view. The export targets a dedicated public bucket and refuses to fall back to the private data bucket, so the browser never receives storage credentials.

The rejected alternatives — one large bundle or a live API — either hide which view failed to upload or reintroduce the hosted database boundary. A manifest lets the SPA show freshness and detect a partial upload while keeping every response cacheable and credential-free.

## Consequences

- Every new view must appear in the snapshot mapping so it is written and recorded in the manifest.
- Changing a view's shape is a contract change and bumps `SCHEMA_VERSION`; consumers can reject a mismatched manifest instead of rendering wrong data.
- The public and private buckets are separate configuration (`R2_BUCKET` vs `R2_PUBLIC_BUCKET`), and a missing public bucket fails the export loudly.
