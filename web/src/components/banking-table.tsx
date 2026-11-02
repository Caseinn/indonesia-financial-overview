import { ArrowDownRight, ArrowUpRight, Minus } from "@phosphor-icons/react"

import { ChartEmpty, InfoPanel } from "@/components/chart-primitives"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { MonthlyOverviewRow } from "@/lib/data"
import { latestPair } from "@/lib/derived"
import { formatMonth, formatPercent, formatSigned } from "@/lib/format"
import { cn } from "@/lib/utils"

type BankingTableProps = {
  data: MonthlyOverviewRow[]
}

type MetricKey = "car" | "roa" | "ldr" | "npl"

const METRICS: {
  key: MetricKey
  label: string
  caption: string
  dot: string
  better: "up" | "down"
}[] = [
  {
    key: "car",
    label: "Capital Adequacy",
    caption: "CAR",
    dot: "bg-chart-1",
    better: "up",
  },
  {
    key: "roa",
    label: "Return on Assets",
    caption: "ROA",
    dot: "bg-chart-2",
    better: "up",
  },
  {
    key: "ldr",
    label: "Loan-to-Deposit",
    caption: "LDR",
    dot: "bg-chart-4",
    better: "up",
  },
  {
    key: "npl",
    label: "Non-Performing Loans",
    caption: "NPL",
    dot: "bg-chart-3",
    better: "down",
  },
]

export function BankingTable({ data }: BankingTableProps) {
  const rows = METRICS.map((metric) => {
    const { latest, previous } = latestPair(data, (row) => row[metric.key])
    const current = latest ? latest[metric.key] : null
    const prior = previous ? previous[metric.key] : null
    const change =
      current !== null && prior !== null ? current - prior : null
    return { ...metric, latest, current, change }
  })

  if (rows.every((row) => row.latest === null)) {
    return <ChartEmpty>No banking indicators published yet.</ChartEmpty>
  }

  return (
    <div>
      <Table>
        <TableHeader>
          <TableRow className="border-line hover:bg-transparent">
            <TableHead className="h-8 pl-2 text-[10px] uppercase tracking-[0.14em] text-muted-ink">
              Indicator
            </TableHead>
            <TableHead className="h-8 text-right text-[10px] uppercase tracking-[0.14em] text-muted-ink">
              Latest
            </TableHead>
            <TableHead className="h-8 pr-0 text-right text-[10px] uppercase tracking-[0.14em] text-muted-ink">
              MoM
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const favourable =
              row.change === null
                ? null
                : row.better === "up"
                  ? row.change > 0
                  : row.change < 0
            const flat = row.change === null || row.change === 0
            return (
              <TableRow key={row.key} className="border-line/80 hover:bg-secondary/40">
                <TableCell className="py-3 pl-2">
                  <div className="flex items-center gap-3">
                    <span className={cn("size-1.5 shrink-0 rounded-full", row.dot)} />
                    <div>
                      <p className="font-serif text-[14px] leading-tight text-navy">
                        {row.label}
                      </p>
                      <p className="text-[10px] uppercase tracking-[0.12em] text-muted-ink">
                        {row.caption}
                        {row.latest ? ` \u00b7 ${formatMonth(row.latest.month_start)}` : ""}
                      </p>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="py-3 text-right font-serif text-lg text-navy tabular-nums">
                  {formatPercent(row.current)}
                </TableCell>
                <TableCell className="py-3 pr-0 text-right">
                  <span
                    className={cn(
                      "inline-flex items-center justify-end gap-1 text-xs tabular-nums",
                      flat
                        ? "text-muted-ink"
                        : favourable
                          ? "text-teal"
                          : "text-orange",
                    )}
                  >
                    {flat ? (
                      <Minus className="size-3" />
                    ) : (row.change ?? 0) > 0 ? (
                      <ArrowUpRight className="size-3" />
                    ) : (
                      <ArrowDownRight className="size-3" />
                    )}
                    {formatSigned(row.change)}
                    <span className="text-[9px] uppercase tracking-wide">pp</span>
                  </span>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>

      <InfoPanel>
        Latest month compared with the month before, in percentage points. NPL moves in the
        opposite direction from the other three ratios.
      </InfoPanel>
    </div>
  )
}
