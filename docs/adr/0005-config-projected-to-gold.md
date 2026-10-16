# Configuration is projected to Gold, not copied

Indicator definitions, Regimes, drift thresholds, and expected release cadence live in `config/indicators.yml` — one file, no duplication in adapter code or SQL. Gold exposes read-only projections of that configuration (`gold.dim_indicator_regimes`; cadence inputs to `gold.vw_dashboard_freshness`), so dashboards render regime-change annotations and staleness from data instead of hardcoded chart marks.

The rejected alternative — maintaining the same constants in YAML, Python, and SQL — guarantees drift between exactly the layers that must agree.

## Consequences

- Changing an indicator's definition is a config commit, not a migration.
- Gold config projections are rebuilt from YAML on every run; they are never hand-edited.
- A rebuild also removes a Source or geography dropped from YAML, and blocks (rather than deletes data) when a dropped Indicator still has facts.
