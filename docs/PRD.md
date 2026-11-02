# PRD: Indonesia Financial Overview

A small, production-minded data platform for Indonesian macroeconomic and financial indicators. Official data flows from source publications through immutable object storage and normalized Parquet into a Parquet Gold layer, and out to a public web dashboard as static JSON snapshots. All sources verified live 15 October 2026.

## Goal

One trustworthy, reproducible pipeline: official source → Bronze → Silver → Gold → static JSON → web dashboard. If a source revises history, the change is traceable and downstream tables rebuild consistently.

## Stack (Free-Tier-First)

| Layer | Tool | Role |
| --- | --- | --- |
| Orchestration | GitHub Actions | Daily availability probes + `workflow_dispatch` backfills |
| Bronze | Cloudflare R2 | Immutable raw edition files + manifests + checksums |
| Processing | Python 3.12 (uv-managed), Pandas, PyArrow, xlrd, openpyxl | Adapters, normalization, Parquet |
| Gold | Parquet in R2 | Facts and views rebuilt from Silver on every Run |
| Presentation | React + Vite SPA on Vercel | Reads static JSON snapshots from a public R2 prefix; never queries Gold |

Non-goals: Airflow, Spark, Kafka, dbt Cloud, live public database access.

## Sources (Verified October 2026)

| ID | Source | Data | Access |
| --- | --- | --- | --- |
| `BI_SEKI` | Bank Indonesia SEKI | Policy rate + interest-rate corridor (TABEL I.25.A/B), USD/IDR monthly middle rate (V.40), later monetary/fiscal/real/external tables | One ZIP per edition from the edition page |
| `BI_JISDOR` | Bank Indonesia JISDOR | Daily USD/IDR reference rate | Bulk via date-range form POST on the JISDOR page (`ButtonExport` → `.xlsx`), proven 15 Oct 2026; BI documents revisions inline |
| `BPS` | BPS | Inflation, regional GDP | WebAPI (JSON), file fallback |
| `OJK_SPI` | OJK Indonesia Banking Statistics | NPL, CAR, LDR, ROA, credit by sector | SJKPublic portal only from the July 2025 data period (`data.ojk.go.id/SJKPublic`); edition pages frozen at June 2025, annual history backfill under distinct `*_ANNUAL` codes — see ADR-0007 |
| `KEMENKEU` | Ministry of Finance (optional) | APBN revenue/expenditure, debt | Publications |

Verified facts that shape ingestion:

- SEKI editions publish between the 15th and 25th of the following month. The edition ZIP is the canonical Publication artifact: atomic, cross-table consistent, one checksum per edition. The standalone per-table `.xls` files are byte-identical to the ZIP members (verified by SHA-256) and are overwritten in place every edition (an emergency fallback only).
- Missing editions soft-404 (`302` → `/id/e404.aspx`); artifact links are resolved from each edition page, never guessed from naming patterns. The canonical SEKI landing page is `/id/statistik/ekonomi-keuangan/seki/`; the former `/en/statistik/ekonomi-moneter/sekilas-indonesia/` path is dead.
- BI's WAF throttles request bursts until they fail outright; adapters pace requests, reuse sessions, and retry with backoff.
- `TABEL1_25_1.xls` carries the policy rate and corridor on sheet-qualified rows (`1.25A_1` "Policy Rate", `1.25A_2` "Deposit Facility" and "Lending Facility dan Financing") plus era sheets reaching back to 1990.
- SEKI files are legacy `.xls` (BIFF). Files load through a magic-byte sniffer (`D0 CF 11 E0` → xlrd, `50 4B 03 04` → openpyxl, HTML/XML fallback), never by file extension.
- Each Publication carries a `table_manifest` with per-file SHA-256 hashes; a re-published ZIP re-parses only tables whose bytes changed.
- SEKI's June 2025 release introduced statistical concept revisions; Regimes record definitional breaks as data.
- OJK moved SPI publication to the SJKPublic portal as of the July 2025 data period; edition pages end at June 2025, and OJK's `Mapping Statistik Perbankan SPI.xlsx` maps old report tables to portal datasets.
- SEKI section IV republishes Kemenkeu APBN data (revenue, expenditure, financing, SBN), which is the preferred fiscal channel over scraping kemenkeu.go.id publications.
- SJKPublic's _metadata_ is an unauthenticated DevExtreme JSON cascade: `GetIndustriData` → `GetInformasiData?industriId=` → `GetMetricData?informasiId=` → `GetGridMeasure?refMetricId=`; the measure _values_ come from a DevExpress `XmlaStore` (`POST /SJKPublic/datasource/`, one catalog/cube per metric) queried with **MDX over SOAP**, not JSON (proven 15 Oct 2026). The store params and the MDX are the adapter contract; Bronze stores both the metadata JSON and the XMLA responses as artifacts.
## Data Contracts

Each adapter returns a standard envelope (`source_id`, `source_url`, `retrieved_at`, `period_start`, `period_end`, `source_file_sha256`, `ingestion_run_id`, `source_version`). One adapter's failure never erases another's successful ingestion. Parsers validate structure against expectations and fail loudly on drift.

`CONTEXT.md` governs vocabulary: Edition, Publication, Observation, Reporting Period, Series, Vintage, Revision, Regime, Run, Source Run, Seed, Circuit Breaker.

## Storage Layout

```
bronze/source=<id>/edition_period=<period>/publication_checksum=<sha256>/artifact + manifest.json
silver/<dataset>/source=<id>/year=<year>/part-000.parquet
```

Bronze is append-only and write-once; a re-released edition is a new Publication whose manifest records `supersedes`. Silver is long-form observations partitioned by year, preserving original values and the original Indonesian source label alongside normalized ones.

## Data Model

**Silver: `macro_observations`** (Parquet in R2; never copied into a database). Business key excludes the checksum; the checksum is lineage. `dimension_code` is the optional second axis (an industry sector, bank group, or credit quality) and is empty for single-series indicators.

```
source_id, source_table, indicator_code,
period_start, period_end, frequency, geography_code, dimension_code,
original_value, original_unit, normalized_value, normalized_unit,
source_raw_label, retrieved_at, source_file_sha256, ingestion_run_id,
is_current, superseded_at
PRIMARY KEY (source_id, source_table, indicator_code, period_start, geography_code, dimension_code)
```

Revisions upsert: old row gets `is_current = false, superseded_at = now`, new row inserted. Gold reads current rows only.

**Gold**

- Dimensions: `dim_source` (projected from `indicators.yml`) and `dim_events` (curated Seed)
- Facts: `fact_macro_periodic` — grain `(indicator_key, period_start, frequency, entity_code default 'IDN', sector_code default 'ALL')`; `fact_market_daily` — grain `(indicator_key, obs_date, entity_code)`; USD/IDR now. Facts are current rows only, embedding revision metadata (`first_published_value`, `revision_count`, `last_revised_at`) derived at projection time from Silver, never authoritative
- Snapshot views: `fx_monthly` (trading EOP + monthly average + `is_complete_month` flag), `financial_overview_monthly` (dashboard core), `financial_overview_annual` (annual fiscal series + pre-portal `*_ANNUAL` ratios), `dashboard_freshness` (per-source lag + global health in one view), `gold_revisions` (superseded Silver rows)

Mixed frequencies are never equated at join time; the dashboard compares via explicit rules on exposed frequency. Monthly FX aggregates are derived views, never stored rows.

## Quality Gates (Block Gold Publish)

Uniqueness at grain; completeness of required fields and periods; validity of units and frequencies; plausibility flags (never auto-delete; real shocks exist); reconciliation against official totals (SEKI V.40 validates `vw_fx_monthly` once JISDOR lands); freshness vs configured cadence; lineage to Publication + Run.

**Zero vs Nothing to Measure:** a source that has not published a period is `skipped/pending`, never a zero row; zeros only exist where the source published one.

**Two-tier drift response:** WARN writes the data and fires the webhook; Circuit Breaker (e.g. >500 bp policy-rate jump, NULL wipeout, >30% of historical rows vanishing) quarantines the Publication and halts that source's Gold promotion. Thresholds are per-indicator config (`relative | absolute_bp | absolute_val`); rates default to 25 bp warn / 500 bp breaker.

## Orchestration

A lightweight availability probe runs daily at 02:30 UTC on the 15th–28th (the SEKI release window) plus weekdays for BI_JISDOR; against the latest `ops` record the probe is a near-no-op once the target edition is ingested. Every Source Run writes its own JSON record under `ops/runs` in R2, and Gold is rebuilt from Silver after all Sources finish, so a quarantined Source shows its previous value. Cross-source reconciliation runs non-blocking afterwards. Known free-tier constraint handled explicitly: GitHub's 60-day schedule auto-disable (failure notifications + periodic activity).

M1 builds the JISDOR adapter directly against the proven bulk path: a date-range form POST (`TextBoxFrom`/`TextBoxDateTo` + `ButtonExport`) returns a multi-month `.xlsx` (no pagination scraping); export dates arrive as M/D/YYYY strings and the sheet carries three junk title rows. SEKI's monthly V.40 rate remains the reconciliation cross-check.

## Dashboard Delivery

`pipeline.gold` rebuilds the views from Silver and `pipeline.export_web` writes one JSON snapshot per dashboard view to the public R2 prefix (`web/data` by default), plus a `manifest.json` recording the Run, `SCHEMA_VERSION`, and per-file checksums so the frontend can show freshness and detect a partial upload. The React + Vite SPA in `web/` deploys to Vercel and reads only those static snapshots; no credentials reach the browser. The pipeline exports the snapshot on every run; to refresh the dashboard without re-running the sources, run `uv run python -m pipeline.export_web`, which rebuilds Gold from Silver and rewrites the Gold Parquet tables.

## Milestones

1. **Vertical slice (BI)**: `POLICY_RATE` plus raw corridor codes (`BI7DR`, `BI_RATE`, `DF_RATE`, `LF_RATE`), money supply, USD/IDR, SEKI parsing from 2019, pre-2019 history from era sheets (static seed only for verified gaps), Gold Parquet tables, ops records, first quality gates, first Gold view and freshness published.
2. **BPS**: inflation and GDP growth via WebAPI (file fallback), with comparison periods and calculation rules defined per frequency.
3. **OJK**: banking metrics via SJKPublic after a timeboxed download spike (ADR-0007) — credit by sector via `sector_code`, NPL, CAR, LDR, ROA.
4. **Context and presentation**: regional context (PHL, VNM, MYS, CHN, THA, SGP via SEKI IX tables), curated event dataset (a Seed), Kemenkeu fiscal data via SEKI section IV tables.

## Deliverables

Versioned raw history in R2; validated Silver Parquet; documented Gold Parquet schema; automated probe + ingestion workflow; quality, drift, and freshness reports; public web dashboard served from static JSON snapshots; source access notes for JISDOR (export POST) and SJKPublic (JSON cascade); reproducible backfill instructions (`workflow_dispatch` with date range); README covering architecture, lineage, deployment.
