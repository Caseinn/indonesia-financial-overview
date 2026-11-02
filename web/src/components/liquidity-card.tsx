import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceDot, XAxis, YAxis } from "recharts"

import { ChartEmpty, LegendItem, PanelHeading, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import {
  WINDOW_START,
  axisTick,
  formatOne,
  gridProps,
  yearTickFormatter,
} from "@/lib/charting"
import type { LiquidityRow } from "@/lib/data"
import { lastNonNull, monthlyGrowth, round2 } from "@/lib/derived"
import { formatMonth, formatPercent } from "@/lib/format"
import { useYearTickInterval } from "@/lib/use-year-tick-interval"

const growthConfig = {
  m1_yoy: { label: "M1 Growth (%)", color: "var(--chart-1)" },
  m2_yoy: { label: "M2 Growth (%)", color: "var(--chart-2)" },
} satisfies ChartConfig

const shareConfig = {
  share: { label: "M1 Share (%)", color: "var(--chart-4)" },
} satisfies ChartConfig

type LiquidityCardProps = {
  data: LiquidityRow[]
}

export function LiquidityCard({ data }: LiquidityCardProps) {
  const m1 = monthlyGrowth(data, "m1")
  const m2 = monthlyGrowth(data, "m2")
  const m2ByMonth = new Map(m2.map((row) => [row.period_start, row]))
  const levels = new Map(data.map((row) => [row.period_start, row]))

  const rows = m1
    .filter((row) => row.period_start >= WINDOW_START)
    .map((row) => {
      const m2Row = m2ByMonth.get(row.period_start)
      const level = levels.get(row.period_start)
      const m1Value = level?.m1
      const m2Value = level?.m2
      const share =
        m1Value !== null &&
        m1Value !== undefined &&
        m2Value !== null &&
        m2Value !== undefined &&
        m2Value !== 0
          ? round2((m1Value / m2Value) * 100)
          : null
      return {
        label: formatMonth(row.period_start),
        m1_yoy: row.yoy,
        m2_yoy: m2Row?.yoy ?? null,
        share,
      }
    })

  const [chartRef, interval] = useYearTickInterval(rows.length)

  if (rows.length === 0) {
    return <ChartEmpty>No liquidity data published yet.</ChartEmpty>
  }

  const m1Latest = lastNonNull(rows, (row) => row.m1_yoy)
  const m2Latest = lastNonNull(rows, (row) => row.m2_yoy)
  const shareLatest = rows.at(-1)

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-ink">
        <div className="flex items-center gap-4">
          <LegendItem color="var(--chart-1)" label="M1 Growth" />
          <LegendItem color="var(--chart-2)" label="M2 Growth" />
        </div>
        <span className="uppercase tracking-[0.12em]">YoY, %</span>
      </div>

      <ChartContainer ref={chartRef} config={growthConfig} className="aspect-auto h-47 w-full">
        <LineChart data={rows} margin={{ left: 0, right: 44, top: 8, bottom: 0 }}>
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
            width={34}
            tickFormatter={(value: number) => `${value}%`}
            tick={axisTick}
          />
          <ChartTooltip
            content={<ValueTooltip config={growthConfig} format={formatOne} />}
            cursor={{ stroke: "var(--color-line)" }}
          />
          <Line
            dataKey="m1_yoy"
            type="monotone"
            stroke="var(--chart-1)"
            strokeWidth={1.8}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="m2_yoy"
            type="monotone"
            stroke="var(--chart-2)"
            strokeWidth={1.8}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          {m1Latest ? (
            <ReferenceDot
              x={m1Latest.label}
              y={m1Latest.m1_yoy ?? 0}
              r={3}
              fill="var(--chart-1)"
              stroke="var(--color-paper)"
              strokeWidth={2}
              label={{
                value: formatPercent(m1Latest.m1_yoy, 1),
                position: "right",
                fill: "var(--chart-1)",
                fontSize: 9,
              }}
            />
          ) : null}
          {m2Latest ? (
            <ReferenceDot
              x={m2Latest.label}
              y={m2Latest.m2_yoy ?? 0}
              r={3}
              fill="var(--chart-2)"
              stroke="var(--color-paper)"
              strokeWidth={2}
              label={{
                value: formatPercent(m2Latest.m2_yoy, 1),
                position: "right",
                fill: "var(--chart-2)",
                fontSize: 9,
              }}
            />
          ) : null}
        </LineChart>
      </ChartContainer>

      <div className="my-3 border-t border-line/80" />

      <PanelHeading
        label="M1 Share of M2"
        meta={shareLatest ? formatPercent(shareLatest.share, 1) : undefined}
      />

      <ChartContainer config={shareConfig} className="aspect-auto h-19.5 w-full">
        <BarChart data={rows} margin={{ left: 0, right: 0, top: 2, bottom: 0 }}>
          <XAxis dataKey="label" hide />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={34}
            tickFormatter={(value: number) => `${value}%`}
            tick={axisTick}
          />
          <ChartTooltip
            content={<ValueTooltip config={shareConfig} format={formatOne} />}
            cursor={{ fill: "var(--color-line)", fillOpacity: 0.25 }}
          />
          <Bar
            dataKey="share"
            fill="var(--chart-4)"
            fillOpacity={0.55}
            barSize={4}
            isAnimationActive={false}
          />
        </BarChart>
      </ChartContainer>
    </div>
  )
}
