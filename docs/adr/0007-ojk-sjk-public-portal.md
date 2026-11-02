# OJK SPI comes from the SJKPublic portal; frozen edition pages are history only

As of the July 2025 data period, OJK publishes Statistik Perbankan Indonesia exclusively through the Integrated Financial Sector Data Portal (`data.ojk.go.id/SJKPublic`); the monthly edition pages stopped at June 2025. The adapter therefore has two access modes: SJKPublic datasets for periods from July 2025 onward, and edition-page artifacts for the historical backfill. A timeboxed spike on SJKPublic's download endpoints runs before M3, and OJK's published `Mapping Statistik Perbankan SPI.xlsx` seeds the old-table-to-dataset mapping in `config/indicators.yml`.

The rejected alternative — keeping the adapter on edition pages — tracks a channel OJK has already retired and would strand all post-July 2025 data.

## Consequences

- SJKPublic coverage starts at the July 2025 period; earlier periods are a one-time backfill from the frozen pages, and the two coverages stay disjoint.
- The pre-portal ratios carry their own `*_ANNUAL` indicator codes because their natural frequency is annual; `dim_indicator.frequency` stays truthful, the monthly view stays monthly-only, and `vw_financial_overview_annual` surfaces the annual series.
- The portal splits into two protocols, both unauthenticated and confirmed live 15 October 2026: a DevExtreme JSON cascade for metadata (`GetIndustriData` → `GetInformasiData` → `GetMetricData` → `GetGridMeasure`) and a DevExpress `XmlaStore` for the measure values (`POST /SJKPublic/datasource/`, catalog/cube per metric), queried as **MDX over SOAP**. The adapter speaks both; Bronze stores the metadata JSON and the XMLA responses as artifacts.
- The mapping document is input, not truth: portal datasets it cannot place fail loudly like any other drift.
- A failed spike escalates instead of blocking: artifacts can be downloaded manually into Bronze with full provenance, leaving Silver and Gold untouched.
