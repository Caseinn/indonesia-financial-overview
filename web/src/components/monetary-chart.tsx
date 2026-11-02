import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts"

import { ChartEmpty, LegendItem, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import {
  WINDOW_START,
  axisTick,
  formatTwo,
  gridProps,
  yearTickFormatter,
} from "@/lib/charting"
import type { MonetaryPolicyRow } from "@/lib/data"
import { lastNonNull } from "@/lib/derived"
import { formatMonth, formatPercent } from "@/lib/format"
import { useYearTickInterval } from "@/lib/use-year-tick-interval"

const chartConfig = {
  policy_rate: { label: "Policy Rate (%)", color: "var(--chart-1)" },
  deposit_facility: { label: "Deposit Facility (%)", color: "var(--chart-2)" },
  lending_facility: { label: "Lending Facility (%)", color: "var(--chart-3)" },
} satisfies ChartConfig

type MonetaryChartProps = {
  data: MonetaryPolicyRow[]
}

type Row = {
  label: string
  policy_rate: number | null
  deposit_facility: number | null
  lending_facility: number | null
  corridor_base: number | null
  corridor: number | null
}

export function MonetaryChart({ data }: MonetaryChartProps) {
  const rows: Row[] = data
    .filter((row) => row.period_start >= WINDOW_START)
    .map((row) => ({
      label: formatMonth(row.period_start),
      policy_rate: row.policy_rate,
      deposit_facility: row.deposit_facility,
      lending_facility: row.lending_facility,
      corridor_base: row.deposit_facility,
      corridor:
        row.deposit_facility !== null && row.lending_facility !== null
          ? row.lending_facility - row.deposit_facility
          : null,
    }))

  const [chartRef, interval] = useYearTickInterval(rows.length)

  if (rows.length === 0) {
    return <ChartEmpty>No policy data published yet.</ChartEmpty>
  }

  const values = rows
    .flatMap((row) => [row.policy_rate, row.deposit_facility, row.lending_facility])
    .filter((value): value is number => value !== null)
  const domain: [number, number] =
    values.length > 0
      ? [Math.floor(Math.min(...values)) - 1, Math.ceil(Math.max(...values)) + 1]
      : [0, 10]

  const policy = lastNonNull(rows, (row) => row.policy_rate)
  const deposit = lastNonNull(rows, (row) => row.deposit_facility)
  const lending = lastNonNull(rows, (row) => row.lending_facility)

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] text-muted-ink">
        <LegendItem color="var(--chart-1)" label="Policy Rate" />
        <LegendItem color="var(--chart-2)" label="Deposit Facility" dashed />
        <LegendItem color="var(--chart-3)" label="Lending Facility" dashed />
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-xs bg-chart-5/50" />
          Corridor
        </span>
      </div>

      <ChartContainer ref={chartRef} config={chartConfig} className="aspect-auto h-85 w-full">
        <ComposedChart data={rows} margin={{ left: 0, right: 54, top: 10, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tickMargin={10}
            interval={interval}
            tickFormatter={yearTickFormatter}
            tick={axisTick}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={42}
            domain={domain}
            tickFormatter={(value: number) => `${value}%`}
            tick={axisTick}
          />
          <ChartTooltip
            content={<ValueTooltip config={chartConfig} format={formatTwo} />}
            cursor={{ stroke: "var(--color-line)" }}
          />
          <Area
            dataKey="corridor_base"
            stackId="corridor"
            stroke="none"
            fill="transparent"
            tooltipType="none"
            isAnimationActive={false}
          />
          <Area
            dataKey="corridor"
            stackId="corridor"
            stroke="none"
            fill="var(--chart-5)"
            fillOpacity={0.45}
            tooltipType="none"
            isAnimationActive={false}
          />
          <ReferenceLine
            x="Jul 2022"
            stroke="#8a7f6a"
            strokeDasharray="4 4"
            strokeOpacity={0.65}
            label={{
              value: "BI-7DR Transition",
              position: "insideTopRight",
              fill: "#6c6656",
              fontSize: 9,
            }}
          />
          <Line
            dataKey="policy_rate"
            type="monotone"
            stroke="var(--chart-1)"
            strokeWidth={2.2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="deposit_facility"
            type="monotone"
            stroke="var(--chart-2)"
            strokeWidth={1.6}
            strokeDasharray="5 3"
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="lending_facility"
            type="monotone"
            stroke="var(--chart-3)"
            strokeWidth={1.6}
            strokeDasharray="5 3"
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          {policy ? (
            <ReferenceDot
              x={policy.label}
              y={policy.policy_rate ?? 0}
              r={3.5}
              fill="var(--chart-1)"
              stroke="var(--color-paper)"
              strokeWidth={2}
              label={{
                value: formatPercent(policy.policy_rate),
                position: "right",
                fill: "var(--chart-1)",
                fontSize: 10,
              }}
            />
          ) : null}
          {deposit ? (
            <ReferenceDot
              x={deposit.label}
              y={deposit.deposit_facility ?? 0}
              r={2.5}
              fill="var(--chart-2)"
              stroke="var(--color-paper)"
              strokeWidth={2}
              label={{
                value: formatPercent(deposit.deposit_facility),
                position: "right",
                fill: "var(--chart-2)",
                fontSize: 10,
              }}
            />
          ) : null}
          {lending ? (
            <ReferenceDot
              x={lending.label}
              y={lending.lending_facility ?? 0}
              r={2.5}
              fill="var(--chart-3)"
              stroke="var(--color-paper)"
              strokeWidth={2}
              label={{
                value: formatPercent(lending.lending_facility),
                position: "right",
                fill: "var(--chart-3)",
                fontSize: 10,
              }}
            />
          ) : null}
        </ComposedChart>
      </ChartContainer>
    </div>
  )
}
