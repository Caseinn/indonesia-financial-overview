# Pre-2019 history comes from SEKI era sheets

The September 2026 edition of `TABEL1_25_1.xls` carries era sheets (`Th 1990-2003`, `Th 2002-2009`, `Th 2010-2016`) reaching back to 1990 with historically consistent policy-rate values, so one parser covers the full history. The adapter parses era sheets and current sheets alike. A static Seed file is built only if fixture work demonstrates a gap the era sheets leave uncovered; until then, no seed exists.

The rejected alternatives: a pre-built seed file duplicates data the source itself republishes, and per-era legacy parsers spend engineering on layouts the current file no longer uses.

## Consequences

- Era-sheet completeness and gap-freeness are an explicit M1 fixture-work gate; until it passes, pre-2019 coverage is provisional.
- If a Seed is ever built, it ships with edition-level provenance, passes the same quality gates as adapter output, and its coverage stays disjoint from adapter coverage.
