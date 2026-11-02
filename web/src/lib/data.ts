export type MonthlyOverviewRow = {
  month_start: string
  policy_rate: number | null
  bi7drr: number | null
  inflation_mom: number | null
  money_supply_m2: number | null
  car: number | null
  roa: number | null
  ldr: number | null
  npl: number | null
  usd_idr_jisdor: number | null
  usd_idr_jisdor_avg: number | null
}

export type MonetaryPolicyRow = {
  period_start: string
  policy_rate: number | null
  bi7drr: number | null
  deposit_facility: number | null
  lending_facility: number | null
}

export type LiquidityRow = {
  period_start: string
  m1: number | null
  m2: number | null
}

export type FiscalAnnualRow = {
  year_start: string
  year: number
  revenue: number | null
  expenditure: number | null
  balance: number | null
}

export type SbnMonthlyRow = {
  period_start: string
  outstanding: number | null
}

export type RupiahRow = {
  month_start: string
  jisdor_eop: number | null
  jisdor_avg: number | null
  seki_rate: number | null
}

export type CreditSectorRow = {
  period_start: string
  dimension_code: string
  value: number
}

export type RegionalRow = {
  period_start: string
  geography_code: string
  gdp_growth: number | null
  inflation: number | null
}

export type FreshnessRow = {
  source_id: string
  name: string
  status: string | null
  last_published_at: string | null
  lag_days: number | null
  refresh_days: number | null
  is_fresh: boolean | null
  rows_published: number | null
  revisions: number | null
  global_healthy: boolean | null
}

export type RevisionRow = {
  indicator_code: string
  period_start: string
  frequency: string
  entity_code: string
  sector_code: string
  first_published_value: number | null
  current_value: number | null
  change: number | null
  revision_count: number
  last_revised_at: string | null
}

export type Manifest = {
  schema_version: number
  run_id: string
  generated_at: string
  views: Record<string, { rows: number; sha256: string }>
}

export type LayoutData = {
  freshness: FreshnessRow[]
  manifest: Manifest
}

export type SeriesData = {
  monthly: MonthlyOverviewRow[]
  monetary: MonetaryPolicyRow[]
  liquidity: LiquidityRow[]
  fiscalAnnual: FiscalAnnualRow[]
  sbn: SbnMonthlyRow[]
  rupiah: RupiahRow[]
  creditSector: CreditSectorRow[]
  regional: RegionalRow[]
  revisions: RevisionRow[]
}

export type DashboardData = LayoutData & SeriesData

export const DATA_BASE_URL = (import.meta.env.VITE_DATA_BASE_URL ?? "")
  .trim()
  .replace(/\/+$/, "")

function snapshotUrl(name: string): string {
  if (!DATA_BASE_URL) {
    throw new Error(
      "VITE_DATA_BASE_URL is not set. Set it to the same-origin proxy prefix, for example /data, then redeploy.",
    )
  }
  return `${DATA_BASE_URL}/${name}.json`
}

async function fetchSnapshot<T>(name: string): Promise<T> {
  const url = snapshotUrl(name)
  const response = await fetch(url, { cache: "no-cache" })
  const contentType = response.headers.get("content-type") ?? "unknown"
  if (!response.ok) {
    throw new Error(`Could not load ${name}.json from ${url} (HTTP ${response.status}).`)
  }
  const text = await response.text()
  if (!contentType.includes("json") && !/^\s*[[{]/.test(text)) {
    throw new Error(
      `${name}.json at ${url} returned ${contentType}, not JSON. VITE_DATA_BASE_URL likely points at the app or a missing object key.`,
    )
  }
  try {
    return JSON.parse(text) as T
  } catch {
    throw new Error(`${name}.json at ${url} is not valid JSON (content-type ${contentType}).`)
  }
}

export async function loadLayout(): Promise<LayoutData> {
  const [freshness, manifest] = await Promise.all([
    fetchSnapshot<FreshnessRow[]>("dashboard_freshness"),
    fetchSnapshot<Manifest>("manifest"),
  ])
  return { freshness, manifest }
}

export async function loadSeries(): Promise<SeriesData> {
  const [
    monthly,
    monetary,
    liquidity,
    fiscalAnnual,
    sbn,
    rupiah,
    creditSector,
    regional,
    revisions,
  ] = await Promise.all([
    fetchSnapshot<MonthlyOverviewRow[]>("financial_overview_monthly"),
    fetchSnapshot<MonetaryPolicyRow[]>("monetary_policy"),
    fetchSnapshot<LiquidityRow[]>("liquidity"),
    fetchSnapshot<FiscalAnnualRow[]>("fiscal_annual"),
    fetchSnapshot<SbnMonthlyRow[]>("sbn_monthly"),
    fetchSnapshot<RupiahRow[]>("rupiah"),
    fetchSnapshot<CreditSectorRow[]>("credit_sector"),
    fetchSnapshot<RegionalRow[]>("regional"),
    fetchSnapshot<RevisionRow[]>("gold_revisions"),
  ])
  return {
    monthly,
    monetary,
    liquidity,
    fiscalAnnual,
    sbn,
    rupiah,
    creditSector,
    regional,
    revisions,
  }
}

let layoutPromise: Promise<LayoutData> | null = null

export function preloadLayout(force = false): Promise<LayoutData> {
  if (force || layoutPromise === null) {
    layoutPromise = loadLayout()
    layoutPromise.catch(() => undefined)
  }
  return layoutPromise
}

export async function loadDashboard(force = false): Promise<DashboardData> {
  const [layout, series] = await Promise.all([preloadLayout(force), loadSeries()])
  return { ...layout, ...series }
}

let dashboardPromise: Promise<DashboardData> | null = null

export function preloadDashboard(force = false): Promise<DashboardData> {
  if (force || dashboardPromise === null) {
    dashboardPromise = loadDashboard(force)
    dashboardPromise.catch(() => undefined)
  }
  return dashboardPromise
}
