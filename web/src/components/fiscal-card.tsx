import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts"

import { ChartEmpty, InfoPanel, LegendItem, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import {
  POINTS_PER_YEAR,
  WINDOW_START,
  axisTick,
  formatOne,
  gridProps,
  yearTickFormatter,
} from "@/lib/charting"
import type { FiscalAnnualRow, SbnMonthlyRow } from "@/lib/data"
import { round2 } from "@/lib/derived"
import { formatCompact, formatMonth } from "@/lib/format"
import { useYearTickInterval } from "@/lib/use-year-tick-interval"

const fiscalConfig = {
  revenue: { label: "Revenue (Rp T)", color: "var(--chart-2)" },
  expenditure: { label: "Expenditure (Rp T)", color: "var(--chart-4)" },
  balance: { label: "Balance (Rp T)", color: "var(--chart-3)" },
} satisfies ChartConfig

const sbnConfig = {
  outstanding: { label: "SBN Outstanding (Rp T)", color: "var(--chart-1)" },
} satisfies ChartConfig

type FiscalCardProps = {
  annual: FiscalAnnualRow[]
  sbn: SbnMonthlyRow[]
}

export function FiscalCard({ annual, sbn }: FiscalCardProps) {
  const fiscalRows = annual
    .filter((row) => row.year >= 2017)
    .map((row) => ({
      year: String(row.year),
      revenue: row.revenue === null ? null : round2(row.revenue / 1000),
      expenditure: row.expenditure === null ? null : round2(row.expenditure / 1000),
      balance: row.balance === null ? null : round2(row.balance / 1000),
    }))

  const sbnRows = sbn
    .filter((row) => row.period_start >= WINDOW_START)
    .map((row) => ({
      label: formatMonth(row.period_start),
      outstanding: row.outstanding === null ? null : round2(row.outstanding / 1000),
    }))

  const [fiscalRef, fiscalInterval] = useYearTickInterval(
    fiscalRows.length,
    POINTS_PER_YEAR.annual,
  )
  const [sbnRef, sbnInterval] = useYearTickInterval(sbnRows.length)

  if (fiscalRows.length === 0 && sbnRows.length === 0) {
    return <ChartEmpty>No fiscal data published yet.</ChartEmpty>
  }

  return (
    <div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-muted-ink">
              Budget Execution
            </p>
            <div className="flex items-center gap-3 text-[10px] text-muted-ink">
              <LegendItem color="var(--chart-2)" label="Revenue" />
              <LegendItem color="var(--chart-4)" label="Spending" />
              <LegendItem color="var(--chart-3)" label="Balance" />
            </div>
          </div>

          <ChartContainer ref={fiscalRef} config={fiscalConfig} className="aspect-auto h-55 w-full">
            <BarChart data={fiscalRows} margin={{ left: 0, right: 4, top: 6, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis
                dataKey="year"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                interval={fiscalInterval}
                tick={axisTick}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={40}
                tickFormatter={(value: number) => formatCompact(value)}
                tick={axisTick}
              />
              <ReferenceLine y={0} stroke="var(--color-line)" />
              <ChartTooltip
                content={<ValueTooltip config={fiscalConfig} format={formatOne} />}
                cursor={{ fill: "var(--color-line)", fillOpacity: 0.25 }}
              />
              <Bar dataKey="revenue" fill="var(--chart-2)" maxBarSize={8} isAnimationActive={false} />
              <Bar
                dataKey="expenditure"
                fill="var(--chart-4)"
                maxBarSize={8}
                isAnimationActive={false}
              />
              <Bar dataKey="balance" fill="var(--chart-3)" maxBarSize={8} isAnimationActive={false} />
            </BarChart>
          </ChartContainer>
        </div>

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-muted-ink">
              SBN Outstanding
            </p>
            <p className="text-[10px] uppercase tracking-[0.12em] text-muted-ink">Monthly Stock</p>
          </div>

          <ChartContainer ref={sbnRef} config={sbnConfig} className="aspect-auto h-55 w-full">
            <AreaChart data={sbnRows} margin={{ left: 0, right: 4, top: 6, bottom: 0 }}>
              <defs>
                <linearGradient id="sbn-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.24} />
                  <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                interval={sbnInterval}
                tickFormatter={yearTickFormatter}
                tick={axisTick}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={40}
                tickFormatter={(value: number) => formatCompact(value)}
                tick={axisTick}
              />
              <ChartTooltip
                content={<ValueTooltip config={sbnConfig} format={formatOne} />}
                cursor={{ stroke: "var(--color-line)" }}
              />
              <Area
                dataKey="outstanding"
                type="monotone"
                stroke="var(--chart-1)"
                strokeWidth={1.8}
                fill="url(#sbn-fill)"
                connectNulls
                isAnimationActive={false}
              />
            </AreaChart>
          </ChartContainer>
        </div>
      </div>

      <InfoPanel>
        Annual budget execution comes from SEKI section IV. SBN outstanding is the monthly stock.
        Both are in trillions of rupiah, converted from the source&apos;s billions.
      </InfoPanel>
    </div>
  )
}
