import type { ReactNode } from "react"

import type { ChartConfig } from "@/components/ui/chart"
import { cn } from "@/lib/utils"

type TooltipItem = {
  dataKey?: string | number
  value?: number | string
  color?: string
}

type ValueTooltipProps = {
  active?: boolean
  payload?: TooltipItem[]
  label?: string | number
  config: ChartConfig
  format?: (value: number, key: string) => string
}

export function ValueTooltip({ active, payload, label, config, format }: ValueTooltipProps) {
  if (!active || !payload?.length) return null
  const seen = new Set<string>()
  const rows = payload.filter((item) => {
    if (item.dataKey === undefined) return false
    if (config[String(item.dataKey)] === undefined) return false
    if (typeof item.value !== "number") return false
    const key = String(item.dataKey)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  if (rows.length === 0) return null

  return (
    <div className="min-w-52 rounded-lg border border-line/80 bg-background px-3 py-2 shadow-[0_10px_24px_rgba(20,42,54,0.12)]">
      {label !== undefined ? (
        <p className="mb-1.5 font-serif text-[11px] text-muted-ink">{String(label)}</p>
      ) : null}
      <ul className="space-y-1">
        {rows.map((item) => {
          const key = String(item.dataKey)
          const entry = config[key]
          const value = item.value as number
          return (
            <li key={key} className="flex items-center justify-between gap-6 text-[11px]">
              <span className="flex items-center gap-1.5 whitespace-nowrap text-muted-ink">
                <span
                  className="size-1.5 rounded-full"
                  style={{ backgroundColor: item.color ?? "var(--chart-1)" }}
                />
                {entry.label ?? key}
              </span>
              <span className="shrink-0 whitespace-nowrap font-mono font-medium tabular-nums text-navy">
                {format ? format(value, key) : value.toLocaleString()}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function InfoPanel({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "mt-4 rounded-md bg-pale/55 px-4 py-3 font-serif text-[12px] leading-relaxed text-ink/70",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function PanelHeading({
  label,
  meta,
}: {
  label: string
  meta?: ReactNode
}) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-2">
      <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-muted-ink">{label}</p>
      {meta ? <p className="text-[10px] uppercase tracking-[0.12em] text-muted-ink">{meta}</p> : null}
    </div>
  )
}

export function LegendItem({
  color,
  label,
  dashed = false,
}: {
  color: string
  label: string
  dashed?: boolean
}) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={cn("w-4", dashed ? "border-t border-dashed" : "h-0.5")}
        style={dashed ? { borderColor: color } : { backgroundColor: color }}
      />
      {label}
    </span>
  )
}

export function ChartEmpty({ children }: { children: ReactNode }) {
  return (
    <p className="py-16 text-center font-serif text-sm text-muted-ink">{children}</p>
  )
}
