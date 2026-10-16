# Indonesia Financial Outlook

Glossary for the Indonesia Financial Outlook platform: the shared vocabulary for ingesting official Indonesian macroeconomic and financial statistics through a Bronze-Silver-Gold pipeline into Tableau.

## Sources and publications

**Source**:
An official institution and its publication channel (BI, BPS, OJK, Kemenkeu), identified by a stable `source_id`.
_Avoid_: agency, provider

**Edition**:
A dated issue of a Source's publication, identified by the reporting period it covers (e.g. the October 2026 SEKI edition). One Edition can yield multiple Publications when a Source re-releases it.
_Avoid_: release, issue

**Publication**:
An immutable, checksummed file artifact of one Edition — the exact bytes the pipeline ingested.
_Avoid_: download, release

**Vintage (As-Of Date)**:
Which Publication a value was known from. The same Reporting Period can carry multiple Vintages when a Source revises history.
_Avoid_: snapshot

## Data

**Indicator**:
A measured economic or financial quantity with a canonical code, unit, and natural frequency (e.g. the policy rate, USD/IDR).
_Avoid_: metric, variable

**Observation**:
A single Indicator value for one Reporting Period and geography.
_Avoid_: data point, measurement

**Reporting Period**:
The time interval an Observation describes, identified by its frequency plus start and end dates.
_Avoid_: period (alone)

**Series**:
A time-ordered sequence of Observations sharing one Indicator, frequency, and unit.
_Avoid_: dataset

**Revision**:
An Observation that supersedes an earlier Observation with the same indicator, reporting period, and geography; superseded values remain part of history.
_Avoid_: correction, update

**Regime**:
A named date range over which an Indicator's definition or source series stayed constant (e.g. the BI-7DR transition of July 2022).
_Avoid_: era, definition period

**Gold Projection**:
The current-state rows projected from Silver into Gold at load time. Revision metadata (`first_published_value`, `revision_count`, `last_revised_at`) is derived during that projection and is never authoritative; Silver remains the only source of revision history.
_Avoid_: mirror, copy

## Execution

**Run**:
One execution of the pipeline.
_Avoid_: job, build

**Source Run**:
One adapter's execution for one Source within a Run.
_Avoid_: task

**Circuit Breaker**:
A drift breach severe enough to quarantine the Publication and halt Gold promotion for that Source.
_Avoid_: fatal error, halt

**Seed**:
A static file of already-normalized historical Observations loaded without a live Source Run; a Seed carries its own provenance.
_Avoid_: fixture (fixtures are for tests)

**Backfill**:
Bulk loading of historical periods, by repeated adapter runs or by Seeds.
_Avoid_: import
