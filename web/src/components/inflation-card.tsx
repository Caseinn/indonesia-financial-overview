import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts"

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
import { INFLATION_TARGET_ERAS } from "@/lib/inflation-target"
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

  const targetBands = INFLATION_TARGET_ERAS.flatMap((era) => {
    const window = points.filter(
      (point) => point.period_start >= era.start && point.period_start <= era.end,
    )
    if (window.length === 0) return []
    return [
      {
        key: era.start,
        x1: window[0].label,
        x2: window[window.length - 1].label,
        y1: era.target - era.corridor,
        y2: era.target + era.corridor,
        label: era.label,
      },
    ]
  })

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
            {targetBands.map((band) => (
              <ReferenceArea
                key={band.key}
                x1={band.x1}
                x2={band.x2}
                y1={band.y1}
                y2={band.y2}
                fill="var(--chart-4)"
                fillOpacity={0.24}
                stroke="none"
                ifOverflow="extendDomain"
                label={{
                  value: band.label,
                  position: "insideTopLeft",
                  fill: "var(--color-muted-ink)",
                  fontSize: 9,
                }}
              />
            ))}
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
        Year-on-year inflation compounds BPS month-over-month changes. Shaded steps show the
        inflation target the Government sets for Bank Indonesia: 4% ±1% in 2017, 3.5% ±1% in 2018
        and 2019, 3% ±1% from 2020 to 2023, and 2.5% ±1% from 2024 to 2027 (PMK 31/2024). Missing
        months stay blank.
      </InfoPanel>
    </div>
  )
}
