# Silver keeps revision history; Gold carries a revision summary

Silver keeps the full revision history of every Observation, keyed by the observation's business key (source, table, indicator, period, geography, dimension) and flagged `is_current`; the source-file checksum is lineage metadata, not part of the key, because a checksum identifies a source version, not an observation. Gold facts hold only current rows, embedding `first_published_value`, `revision_count`, and `last_revised_at` for dashboard revision tooltips, with the `gold_revisions` snapshot exposing superseded Silver rows.

The rejected alternative — checksum in the primary key — made every revision a new indistinguishable "current" row and pushed source-versioning logic into every downstream query.

## Consequences

- Revisions are an upsert: flip `is_current` on the old row, insert the new one.
- Revision history lives in Silver (Parquet/R2) only; Gold stays small and fast.
