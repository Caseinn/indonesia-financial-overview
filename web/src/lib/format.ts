const DASH = "\u2014"

function isMissing(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value)
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (isMissing(value)) return DASH
  return `${value.toFixed(digits)}%`
}

export function formatNumber(
  value: number | null | undefined,
  options: Intl.NumberFormatOptions = {},
): string {
  if (isMissing(value)) return DASH
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
    ...options,
  }).format(value)
}

export function formatCompact(value: number | null | undefined): string {
  if (isMissing(value)) return DASH
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value)
}

export function parseDateOnly(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number)
  return new Date(year, month - 1, day)
}

function toDate(iso: string): Date {
  return iso.length === 10 ? parseDateOnly(iso) : new Date(iso)
}

export function formatMonth(iso: string | null | undefined): string {
  if (!iso) return DASH
  return parseDateOnly(iso).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
  })
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH
  return toDate(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

export function formatSigned(value: number | null | undefined, digits = 2): string {
  if (isMissing(value)) return DASH
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "always",
  }).format(value)
}

export function formatRupiah(value: number | null | undefined): string {
  if (isMissing(value)) return DASH
  return `Rp ${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value)}`
}
