export const WINDOW_START = "2017-01-01"
export const axisTick = { fontSize: 9 } as const
export const POINTS_PER_YEAR = {
  annual: 1,
  quarterly: 4,
  monthly: 12,
} as const

const MIN_YEAR_TICK_GAP = 34
const AXIS_GUTTER = 52

export function yearTickInterval(
  pointCount: number,
  width: number,
  pointsPerYear: number,
): number {
  const perYear = Math.max(1, Math.round(pointsPerYear))
  const years = Math.max(1, Math.ceil(pointCount / perYear))
  const plotWidth = Math.max(0, width - AXIS_GUTTER)
  const maxLabels = Math.max(1, Math.floor(plotWidth / MIN_YEAR_TICK_GAP))
  const stride = Math.max(1, Math.ceil(years / maxLabels))
  return stride * perYear - 1
}

export const gridProps = {
  vertical: false,
  stroke: "var(--color-line)",
  strokeDasharray: "2 5",
} as const

export function yearTickFormatter(value: string | number): string {
  return String(value).slice(-4)
}

export function quarterYearTickFormatter(value: string | number): string {
  return String(value).slice(0, 4)
}

function digits(value: number, places: number): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  }).format(value)
}

export function formatTwo(value: number): string {
  return digits(value, 2)
}

export function formatOne(value: number): string {
  return digits(value, 1)
}

export function formatWhole(value: number): string {
  return digits(value, 0)
}
