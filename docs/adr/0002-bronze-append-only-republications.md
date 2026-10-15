# Bronze is append-only; re-published editions are kept, chained, and diffed

Bronze is write-once, keyed by (source_id, edition_period, file_checksum). When a source re-publishes an edition with changed bytes, the new file is stored as a new object and the manifest records which run it supersedes; nothing is overwritten or deleted. A cell-level diff computed during the Silver transition flags historical value shifts beyond configured thresholds, because silently accepting a changed checksum would also swallow corrupted or truncated re-uploads.

The rejected alternative — treating an unchanged edition_period as "already ingested" — is exactly what makes a checksum change invisible.

## Consequences

- Bronze storage grows with re-publications; accepted as the price of auditability.
- Thresholds live in per-indicator configuration, not in adapter code.
- Each Publication carries a table_manifest with per-file SHA-256 hashes, so a re-published ZIP re-parses only the tables whose bytes changed.
