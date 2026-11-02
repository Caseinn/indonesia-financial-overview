import { Bar, BarChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts"

import { ChartEmpty, InfoPanel, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import {
  WINDOW_START,
  axisTick,
  formatTwo,
  gridProps,
  yearTickFormatter,
} from "@/lib/charting"
import type { MonthlyOverviewRow } from "@/lib/data"
import { inflationYoy } from "@/lib/derived"
import { formatMonth, formatPercent } from "@/lib/format"
import { useYearTickInterval } from "@/lib/use-year-tick-interval"

const chartConfig = {
  yoy: { label: "Inflation YoY (%)", color: "var(--chart-1)" },
} satisfies ChartConfig

type InflationCardProps = {
  data: MonthlyOverviewRow[]
}

export function InflationCard({ data }: InflationCardProps) {
  const points = inflationYoy(data)
    .filter((point) => point.period_start >= WINDOW_START)
    .map((point) => ({
      label: formatMonth(point.period_start),
      yoy: point.yoy,
      period_start: point.period_start,
    }))
  const latest = points.at(-1)
  const [chartRef, interval] = useYearTickInterval(points.length)

  if (points.length === 0) {
    return <ChartEmpty>No inflation history published yet.</ChartEmpty>
  }

  return (
    <div>
      <div className="relative">
        {latest ? (
          <div className="pointer-events-none absolute right-1 top-1 z-10 rounded-[3px] bg-navy px-3 py-2 text-paper shadow-[0_6px_16px_rgba(20,42,54,0.18)]">
            <p className="text-[8px] uppercase tracking-[0.18em] text-paper/65">Latest YoY</p>
            <p className="font-serif text-lg leading-tight tabular-nums">
              {formatPercent(latest.yoy)}
            </p>
            <p className="text-[9px] text-paper/65">{formatMonth(latest.period_start)}</p>
          </div>
        ) : null}

        <ChartContainer ref={chartRef} config={chartConfig} className="aspect-auto h-62 w-full">
          <BarChart data={points} margin={{ left: 0, right: 8, top: 8, bottom: 0 }} barCategoryGap={0}>
            <CartesianGrid {...gridProps} />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tickMargin={9}
              interval={interval}
              tickFormatter={yearTickFormatter}
              tick={axisTick}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={38}
              tickFormatter={(value: number) => `${value}%`}
              tick={axisTick}
            />
            <ReferenceLine y={0} stroke="var(--color-line)" />
            <ChartTooltip
              content={<ValueTooltip config={chartConfig} format={formatTwo} />}
              cursor={{ fill: "var(--color-line)", fillOpacity: 0.3 }}
            />
            <Bar
              dataKey="yoy"
              fill="var(--chart-1)"
              fillOpacity={0.82}
              maxBarSize={4}
              isAnimationActive={false}
            />
          </BarChart>
        </ChartContainer>
      </div>

      <InfoPanel>
        Year-on-year inflation is compounded from BPS month-over-month changes. The chart starts in
        2017. Missing months appear as gaps, not zeros.
      </InfoPanel>
    </div>
  )
}
