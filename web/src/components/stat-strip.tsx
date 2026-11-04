import type { MonthlyOverviewRow } from "@/lib/data"
import { inflationYoy, latestMetric } from "@/lib/derived"
import { formatMonth, formatNumber, formatPercent } from "@/lib/format"
import { cn } from "@/lib/utils"

type StatStripProps = {
  monthly: MonthlyOverviewRow[]
}

type Stat = {
  label: string
  value: string
  note: string
  dot: string
}

export function StatStrip({ monthly }: StatStripProps) {
  const policy = latestMetric(monthly, "policy_rate")
  const inflation = inflationYoy(monthly).at(-1)
  const usd = latestMetric(monthly, "usd_idr_jisdor")
  const npl = latestMetric(monthly, "npl")

  const stats: Stat[] = [
    {
      label: "Policy rate",
      value: formatPercent(policy?.value),
      note: policy ? `As of ${formatMonth(policy.month)}` : "Not published",
      dot: "bg-chart-2",
    },
    {
      label: "Inflation, YoY",
      value: inflation ? formatPercent(inflation.yoy) : "\u2014",
      note: inflation ? `As of ${formatMonth(inflation.period_start)}` : "Not published",
      dot: "bg-chart-3",
    },
    {
      label: "USD/IDR",
      value: formatNumber(usd?.value),
      note: usd ? `As of ${formatMonth(usd.month)}` : "Not published",
      dot: "bg-chart-1",
    },
    {
      label: "NPL ratio",
      value: formatPercent(npl?.value),
      note: npl ? `As of ${formatMonth(npl.month)}` : "Not published",
      dot: "bg-chart-4",
    },
  ]

  return (
    <div className="grid grid-cols-2 border-y border-line bg-background sm:grid-cols-4">
      {stats.map((stat, index) => (
        <div
          key={stat.label}
          className={cn(
            "px-5 py-4 lg:px-6",
            index % 2 === 1 ? "border-l border-line" : "",
            index > 1 ? "border-t border-line sm:border-t-0" : "",
            index > 0 ? "sm:border-l sm:border-line" : "",
          )}
        >
          <div className="flex items-center gap-2">
            <span className={cn("size-1.5 rounded-full", stat.dot)} />
            <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-ink">
              {stat.label}
            </p>
          </div>
          <p className="mt-2 font-serif text-3xl leading-none tracking-[-0.02em] text-navy tabular-nums">
            {stat.value}
          </p>
          <p className="mt-1.5 text-[11px] text-muted-ink">{stat.note}</p>
        </div>
      ))}
    </div>
  )
}
