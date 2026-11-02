import type { LiquidityRow, MonthlyOverviewRow, RegionalRow } from "@/lib/data"

export const SECTOR_LABELS: Record<string, string> = {
  "001": "Agriculture, Forestry & Fishing",
  "002": "Mining & Quarrying",
  "003": "Manufacturing",
  "004": "Electricity & Gas",
  "005": "Water & Waste",
  "006": "Construction",
  "007": "Wholesale & Retail Trade",
  "008": "Transport & Storage",
  "009": "Accommodation & Food",
  "010": "Information & Communication",
  "011": "Finance & Insurance",
  "012": "Real Estate",
  "013": "Professional Services",
  "014": "Rental & Business Support",
  "015": "Public Administration",
  "016": "Education",
  "017": "Health & Social Work",
  "018": "Arts & Recreation",
  "019": "Other Services",
  "020": "Household Employers",
  "021": "International Bodies",
  "022": "Household: Housing",
  "023": "Household: Apartments",
  "024": "Household: Shophouses",
  "025": "Household: Vehicles",
  "026": "Household: Appliances",
  "027": "Household: Other",
  "028": "Other Sectors",
}

export const COUNTRIES = [
  { code: "IDN", name: "Indonesia", color: "var(--chart-1)" },
  { code: "PHL", name: "Philippines", color: "var(--chart-2)" },
  { code: "MYS", name: "Malaysia", color: "var(--chart-4)" },
  { code: "THA", name: "Thailand", color: "var(--chart-3)" },
  { code: "SGP", name: "Singapore", color: "var(--chart-5)" },
  { code: "CHN", name: "China", color: "#8a7f6a" },
] as const

export function monthKey(iso: string): string {
  return iso.slice(0, 7)
}

export function round2(value: number): number {
  return Math.round(value * 100) / 100
}

export function shiftMonth(key: string, delta: number): string {
  const [year, month] = key.split("-").map(Number)
  const shifted = new Date(year, month - 1 + delta, 1)
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, "0")}`
}

export type GrowthPoint = {
  period_start: string
  level: number | null
  yoy: number | null
}

export function monthlyGrowth(rows: LiquidityRow[], key: "m1" | "m2"): GrowthPoint[] {
  const byMonth = new Map(rows.map((row) => [monthKey(row.period_start), row[key]]))
  return rows.map((row) => {
    const level = row[key]
    const previous = byMonth.get(shiftMonth(monthKey(row.period_start), -12))
    const yoy =
      level !== null && previous !== null && previous !== undefined && previous !== 0
        ? round2(((level / previous) - 1) * 100)
        : null
    return { period_start: row.period_start, level, yoy }
  })
}

export type InflationPoint = {
  period_start: string
  yoy: number
}

export function inflationYoy(rows: MonthlyOverviewRow[]): InflationPoint[] {
  const byMonth = new Map(rows.map((row) => [monthKey(row.month_start), row.inflation_mom]))
  const points: InflationPoint[] = []
  for (const row of rows) {
    const key = monthKey(row.month_start)
    let factor = 1
    let complete = true
    for (let offset = 0; offset < 12; offset += 1) {
      const mom = byMonth.get(shiftMonth(key, -offset))
      if (mom === null || mom === undefined) {
        complete = false
        break
      }
      factor *= 1 + mom / 100
    }
    if (complete) {
      points.push({ period_start: row.month_start, yoy: round2((factor - 1) * 100) })
    }
  }
  return points
}

export function quarterLabel(iso: string): string {
  const [year, month] = iso.split("-").map(Number)
  return `${year} Q${Math.floor((month - 1) / 3) + 1}`
}

export type RegionalPivotRow = {
  period_start: string
  label: string
  [country: string]: string | number | null
}

export function regionalPivot(
  rows: RegionalRow[],
  metric: "gdp_growth" | "inflation",
): RegionalPivotRow[] {
  const byQuarter = new Map<string, RegionalPivotRow>()
  for (const row of rows) {
    const key = row.period_start
    const entry = byQuarter.get(key) ?? {
      period_start: key,
      label: quarterLabel(key),
    }
    entry[row.geography_code] = row[metric]
    byQuarter.set(key, entry)
  }
  return [...byQuarter.values()].sort((a, b) => a.period_start.localeCompare(b.period_start))
}

export function commonRegionalRange(
  rows: RegionalPivotRow[],
  codes: readonly string[],
): RegionalPivotRow[] {
  const complete = rows.filter((row) => codes.every((code) => row[code] !== null && row[code] !== undefined))
  if (complete.length === 0) return []
  const start = complete[0].period_start
  const end = complete[complete.length - 1].period_start
  return rows.filter((row) => row.period_start >= start && row.period_start <= end)
}

export function latestPair<T>(
  rows: T[],
  value: (row: T) => number | null,
): { latest: T | null; previous: T | null } {
  let latest: T | null = null
  let previous: T | null = null
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    if (value(rows[index]) === null) continue
    if (latest === null) {
      latest = rows[index]
    } else {
      previous = rows[index]
      break
    }
  }
  return { latest, previous }
}

export function latestMetric(
  rows: MonthlyOverviewRow[],
  key: keyof MonthlyOverviewRow,
): { value: number; month: string } | null {
  const row = lastNonNull(rows, (item) =>
    typeof item[key] === "number" ? (item[key] as number) : null,
  )
  if (!row) return null
  return { value: row[key] as number, month: row.month_start }
}

export function lastNonNull<T>(rows: T[], value: (row: T) => number | null): T | null {
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    if (value(rows[index]) !== null) return rows[index]
  }
  return null
}
