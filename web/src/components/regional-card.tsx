import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"

import { ChartEmpty, InfoPanel, ValueTooltip } from "@/components/chart-primitives"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import {
  POINTS_PER_YEAR,
  WINDOW_START,
  axisTick,
  formatOne,
  gridProps,
  quarterYearTickFormatter,
} from "@/lib/charting"
import type { RegionalRow } from "@/lib/data"
import { COUNTRIES, commonRegionalRange, regionalPivot } from "@/lib/derived"
import { useYearTickInterval } from "@/lib/use-year-tick-interval"

type RegionalCardProps = {
  data: RegionalRow[]
}

const countryCodes = COUNTRIES.map((country) => country.code)

const regionalConfig: ChartConfig = Object.fromEntries(
  COUNTRIES.map((country) => [country.code, { label: `${country.name} (%)`, color: country.color }]),
)

function RegionalPanel({
  title,
  data,
}: {
  title: string
  data: ReturnType<typeof regionalPivot>
}) {
  const [chartRef, interval] = useYearTickInterval(data.length, POINTS_PER_YEAR.quarterly)

  return (
    <div>
      <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-ink">
        {title}
      </p>
      <ChartContainer ref={chartRef} config={regionalConfig} className="aspect-auto h-59.5 w-full">
        <LineChart data={data} margin={{ left: 0, right: 8, top: 6, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            interval={interval}
            tickFormatter={quarterYearTickFormatter}
            tick={axisTick}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={36}
            tickFormatter={(value: number) => `${value}%`}
            tick={axisTick}
          />
          <ChartTooltip
            content={<ValueTooltip config={regionalConfig} format={formatOne} />}
            cursor={{ stroke: "var(--color-line)" }}
          />
          {COUNTRIES.map((country) => (
            <Line
              key={country.code}
              dataKey={country.code}
              type="monotone"
              stroke={country.color}
              strokeWidth={country.code === "IDN" ? 2.2 : 1.5}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ChartContainer>
    </div>
  )
}

export function RegionalCard({ data }: RegionalCardProps) {
  const gdp = commonRegionalRange(
    regionalPivot(data, "gdp_growth").filter((row) => row.period_start >= WINDOW_START),
    countryCodes,
  )
  const inflation = commonRegionalRange(
    regionalPivot(data, "inflation").filter((row) => row.period_start >= WINDOW_START),
    countryCodes,
  )

  if (gdp.length === 0 && inflation.length === 0) {
    return <ChartEmpty>No regional comparison published yet.</ChartEmpty>
  }

  const first = gdp[0]?.label ?? inflation[0]?.label
  const last = gdp.at(-1)?.label ?? inflation.at(-1)?.label

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-muted-ink">
        {COUNTRIES.map((country) => (
          <span key={country.code} className="flex items-center gap-1.5">
            <span className="h-0.5 w-4" style={{ backgroundColor: country.color }} />
            {country.name}
          </span>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <RegionalPanel title="Real GDP Growth, YoY" data={gdp} />
        <RegionalPanel title="Consumer Inflation, YoY" data={inflation} />
      </div>

      <InfoPanel>
        The window runs from {first} to {last}, the latest quarter shared by every country. Source
        series cover Indonesia, the Philippines, Malaysia, Thailand, Singapore, and China.
      </InfoPanel>
    </div>
  )
}
