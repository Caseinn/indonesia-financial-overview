# OJK SPI comes from the SJKPublic portal; frozen edition pages are history only

As of the July 2025 data period, OJK publishes Statistik Perbankan Indonesia exclusively through the Integrated Financial Sector Data Portal (`data.ojk.go.id/SJKPublic`); the monthly edition pages stopped at June 2025. The adapter therefore has two access modes: SJKPublic datasets for periods from July 2025 onward, and edition-page artifacts for the historical backfill. A timeboxed spike on SJKPublic's download endpoints runs before M3, and OJK's published `Mapping Statistik Perbankan SPI.xlsx` seeds the old-table-to-dataset mapping in `config/indicators.yml`.

The rejected alternative — keeping the adapter on edition pages — tracks a channel OJK has already retired and would strand all post-July 2025 data.

## Consequences

- SJKPublic coverage starts at the July 2025 period; earlier periods are a one-time backfill from the frozen pages, and the two coverages stay disjoint.
- The portal's data layer is an unauthenticated DevExtreme JSON cascade (`GetIndustriData` → `GetInformasiData` → `GetMetricData` → `GetGridMeasure`), confirmed live 15 October 2026; the adapter speaks JSON, and Bronze stores the JSON responses as the artifact.
- The mapping document is input, not truth: portal datasets it cannot place fail loudly like any other drift.
- A failed spike escalates instead of blocking: artifacts can be downloaded manually into Bronze with full provenance, leaving Silver and Gold untouched.
