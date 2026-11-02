import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { ChartEmpty, InfoPanel, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import {
  WINDOW_START,
  axisTick,
  formatWhole,
  gridProps,
  yearTickFormatter,
} from "@/lib/charting"
import type { RupiahRow } from "@/lib/data"
import { lastNonNull } from "@/lib/derived"
import { formatCompact, formatMonth, formatRupiah } from "@/lib/format"
import { useYearTickInterval } from "@/lib/use-year-tick-interval"

type RupiahCardProps = {
  data: RupiahRow[]
}

type Point = {
  label: string
  jisdor: number | null
  seki: number | null
}

const jisdorConfig = {
  jisdor: { label: "JISDOR (Rp/USD)", color: "var(--chart-1)" },
} satisfies ChartConfig

const sekiConfig = {
  seki: { label: "SEKI Middle Rate (Rp/USD)", color: "var(--chart-1)" },
} satisfies ChartConfig

function RatePanel({
  title,
  dataKey,
  gradientId,
  config,
  points,
  note,
}: {
  title: string
  dataKey: "jisdor" | "seki"
  gradientId: string
  config: ChartConfig
  points: Point[]
  note: string
}) {
  const latest = lastNonNull(points, (point) => point[dataKey])
  const [chartRef, interval] = useYearTickInterval(points.length)

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-[0.16em] text-muted-ink">{title}</p>
          <p className="mt-1.5 inline-block rounded-[3px] bg-navy px-2.5 py-1 font-serif text-base leading-none text-paper tabular-nums">
            {latest ? formatRupiah(latest[dataKey]) : "\u2014"}
          </p>
        </div>
        <p className="text-[10px] text-muted-ink">{latest ? latest.label : note}</p>
      </div>

      <ChartContainer ref={chartRef} config={config} className="aspect-auto h-44 w-full">
        <AreaChart data={points} margin={{ left: 0, right: 6, top: 6, bottom: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-4)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--chart-4)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid {...gridProps} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            interval={interval}
            tickFormatter={yearTickFormatter}
            tick={axisTick}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(value: number) => formatCompact(value)}
            tick={axisTick}
          />
          <ChartTooltip
            content={<ValueTooltip config={config} format={formatWhole} />}
            cursor={{ stroke: "var(--color-line)" }}
          />
          <Area
            dataKey={dataKey}
            type="monotone"
            stroke="var(--chart-1)"
            strokeWidth={1.8}
            fill={`url(#${gradientId})`}
            connectNulls
            isAnimationActive={false}
          />
        </AreaChart>
      </ChartContainer>
    </div>
  )
}

export function RupiahCard({ data }: RupiahCardProps) {
  const points: Point[] = data
    .filter((row) => row.month_start >= WINDOW_START)
    .map((row) => ({
      label: formatMonth(row.month_start),
      jisdor: row.jisdor_eop,
      seki: row.seki_rate,
    }))

  if (points.length === 0) {
    return <ChartEmpty>No exchange-rate history published yet.</ChartEmpty>
  }

  return (
    <div>
      <div className="grid gap-6 sm:grid-cols-2">
        <RatePanel
          title="JISDOR Reference Rate"
          dataKey="jisdor"
          gradientId="jisdor-fill"
          config={jisdorConfig}
          points={points}
          note="Daily, month-end"
        />
        <RatePanel
          title="SEKI Middle Rate"
          dataKey="seki"
          gradientId="seki-fill"
          config={sekiConfig}
          points={points}
          note="Monthly"
        />
      </div>
      <InfoPanel>
        JISDOR is Bank Indonesia&apos;s daily reference rate. SEKI is the monthly middle rate. Both
        are rupiah per US dollar.
      </InfoPanel>
    </div>
  )
}
