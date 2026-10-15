# Gold publishes one transaction per source

Each Source publishes to Gold in its own transaction; a failing Source blocks only itself, so an OJK parser failure can never erase a successful BI ingestion. Cross-source reconciliation runs non-blocking after all loads, and the freshness view makes per-source lag visible in the dashboard.

The rejected alternative — a single atomic transaction across all sources — maximized cross-source consistency but let one failure erase every other Source's fresh data.

## Consequences

- Mid-run, Gold can hold Sources at different Vintages; the freshness view surfaces this rather than hiding it.
- `ops` audit tables record one row per Run and one row per Source Run, not one row per Run overall.
