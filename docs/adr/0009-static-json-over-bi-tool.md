# No BI tool; the dashboard reads static JSON snapshots

The public dashboard is a React + Vite SPA that reads pre-built JSON snapshots from a public R2 prefix. Tableau, Metabase, and Looker are not connected to the pipeline because each needs a live query source plus credentials, which conflicts with the project boundary that no database is exposed and no secrets reach the browser. A custom SPA also keeps full control over the editorial layout and chart semantics that the dashboard depends on.

The rejected alternative — embedding Tableau or pointing Metabase at a SQL source — would require standing up the hosted database rejected in ADR-0008, handing a third party access to pipeline credentials, and accepting a vendor's chart defaults for a presentation whose whole point is a specific editorial style.

## Consequences

- Chart primitives, formatting, and empty/skeleton states are maintained in `web/`; there is no drag-and-drop analysis surface for the public.
- Internal ad-hoc analysis can read Silver or Gold Parquet with pandas and PyArrow without changing the public path.
- Adding a dashboard view means changing both the Gold projection and the snapshot export contract (ADR-0010), not configuring a report.
