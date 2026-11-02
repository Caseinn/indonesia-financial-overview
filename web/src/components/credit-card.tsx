import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"

import { ChartEmpty, PanelHeading, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { axisTick, formatOne } from "@/lib/charting"
import type { CreditSectorRow } from "@/lib/data"
import { SECTOR_LABELS, round2 } from "@/lib/derived"
import { formatMonth, formatNumber, formatPercent } from "@/lib/format"

const chartConfig = {
  share: { label: "Share of Credit (%)", color: "var(--chart-4)" },
} satisfies ChartConfig

type CreditCardProps = {
  data: CreditSectorRow[]
}

export function CreditCard({ data }: CreditCardProps) {
  if (data.length === 0) {
    return <ChartEmpty>No sector credit published yet.</ChartEmpty>
  }

  const period = data[0].period_start
  const total = data.reduce((sum, row) => sum + row.value, 0)
  const rows = [...data]
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
    .map((row) => {
      const share = total === 0 ? 0 : round2((row.value / total) * 100)
      return {
        label: SECTOR_LABELS[row.dimension_code] ?? `Sector ${row.dimension_code}`,
        share,
        shareLabel: `${share.toFixed(1)}%`,
        value: row.value,
      }
    })

  const top = rows[0]

  return (
    <div className="grid gap-6 lg:grid-cols-[1.7fr_1fr]">
      <div>
        <PanelHeading label="Largest Exposures" meta={formatMonth(period)} />

        <ChartContainer config={chartConfig} className="aspect-auto h-87 w-full">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ left: 4, right: 44, top: 4, bottom: 4 }}
            barCategoryGap={6}
          >
            <CartesianGrid horizontal={false} stroke="var(--color-line)" strokeDasharray="2 5" />
            <XAxis
              type="number"
              domain={[0, "dataMax + 4"]}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => `${value}%`}
              tick={axisTick}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={132}
              tickLine={false}
              axisLine={false}
              tick={axisTick}
            />
            <ChartTooltip
              content={<ValueTooltip config={chartConfig} format={formatOne} />}
              cursor={{ fill: "var(--color-line)", fillOpacity: 0.25 }}
            />
            <Bar
              dataKey="share"
              fill="var(--chart-4)"
              fillOpacity={0.82}
              barSize={10}
              radius={[0, 2, 2, 0]}
              isAnimationActive={false}
            >
              <LabelList
                dataKey="shareLabel"
                position="right"
                className="fill-muted-ink"
                fontSize={9}
              />
            </Bar>
          </BarChart>
        </ChartContainer>
      </div>

      <div className="flex flex-col justify-between gap-5 rounded-md bg-pale/55 px-4 py-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.16em] text-muted-ink">
            Total Bank Credit
          </p>
          <p className="mt-1 font-serif text-3xl leading-none text-navy tabular-nums">
            {formatNumber(total / 1e12)}
            <span className="ml-1 text-base text-muted-ink">T</span>
          </p>
          <p className="mt-1 text-[11px] text-muted-ink">
            Trillions of rupiah, all reporting sectors
          </p>
        </div>

        <div className="space-y-3 border-t border-line/80 pt-4">
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-ink">Largest Sector</p>
            <p className="mt-0.5 font-serif text-sm leading-snug text-navy">{top?.label}</p>
            <p className="text-[11px] text-muted-ink">{formatPercent(top?.share, 1)} of total</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-ink">
              Sectors Reported
            </p>
            <p className="mt-0.5 font-serif text-sm text-navy">{data.length}</p>
          </div>
        </div>

        <p className="border-t border-line/80 pt-4 font-serif text-[11px] leading-relaxed text-ink/65">
          Sector labels follow the OJK statistical classification. Shares use all reporting
          sectors as the denominator, including the ones not shown.
        </p>
      </div>
    </div>
  )
}
