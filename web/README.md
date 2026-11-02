# Indonesia Financial Overview Web

React + Vite dashboard for the Gold-layer snapshots exported by the pipeline. It
reads static JSON from a public R2 prefix, never from a live database.

Routes: `/` is the dashboard and `/guide` is a plain-language reading guide for
non-economists. The build writes a `guide.html` variant with its own title,
description, and canonical URL; `vercel.json` rewrites `/guide` to it. Unknown
paths serve `public/404.html` with a real 404 status.

## Develop Locally

The dashboard reads static JSON, so local dev needs a snapshot served by Vite.

1. Install dependencies:

   ```bash
   npm install
   ```

2. Rebuild Gold from Silver and write the JSON locally:

   ```bash
   npm run data:local
   ```

   This runs `uv run --directory .. python -m pipeline.export_web --out web/public/data`
   and needs the `R2_*` credentials plus `R2_BUCKET` in the repository `.env`,
   because Gold is rebuilt from the Silver Parquet in R2.

3. Start the dev server:

   ```bash
   npm run dev
   ```

`web/.env.local` points `VITE_DATA_BASE_URL` at `/data`, which Vite serves from
`web/public/data`. Run `npm run data:local` again after each pipeline run.
`public/data` is gitignored.

To develop against production data instead, set `VITE_DATA_BASE_URL` in
`.env.local` to the public bucket path ending in `web/data`.

## Publish A Snapshot

The dashboard reads whatever the pipeline last exported. To refresh it without
re-running the sources:

```bash
uv run python -m pipeline.export_web
```

This rebuilds Gold from Silver and needs `R2_*` credentials plus
`R2_PUBLIC_BUCKET` pointing at a bucket with public access enabled. Verify with:

```bash
curl https://<public-bucket-domain>/web/data/manifest.json
```

The response must be JSON, not HTML.

## Build

```bash
npm run build
```

## Deploy On Vercel

- Import the repository and set the project root directory to `web`.
- Framework preset: Vite.
- Add `indonesia-financial.web.id` under Project → Domains, then point the
  registrar's DNS at Vercel (apex `A` to `76.76.21.21`, `www` `CNAME` to
  `cname.vercel-dns.com`). `.web.id` cannot be a Cloudflare zone, so an R2
  custom domain is not an option here.
- Production values live in `web/.env.production` and are committed:
  `VITE_DATA_BASE_URL=/data` and `VITE_SITE_URL=https://indonesia-financial.web.id`.
  Vercel environment variables override them.
- The `/data/:path*` rewrite in `vercel.json` proxies the public R2 prefix
  through the same origin, so the browser never calls R2 and no bucket CORS rule
  is needed. Its destination is the only hardcoded value, because rewrites
  cannot read environment variables.

The pipeline writes `manifest.json` next to the view files; the dashboard reads
its `generated_at` timestamp to show snapshot freshness.
