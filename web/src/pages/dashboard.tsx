import { useEffect, useState } from "react"
import { useLocation } from "react-router-dom"

import { BankingTable } from "@/components/banking-table"
import { CreditCard } from "@/components/credit-card"
import { EditorialHeader } from "@/components/editorial-header"
import { FiscalCard } from "@/components/fiscal-card"
import { InflationCard } from "@/components/inflation-card"
import { LiquidityCard } from "@/components/liquidity-card"
import { MonetaryChart } from "@/components/monetary-chart"
import { RegionalCard } from "@/components/regional-card"
import { RupiahCard } from "@/components/rupiah-card"
import { SectionCard } from "@/components/section-card"
import { SocialLinks } from "@/components/social-links"
import { StatStrip } from "@/components/stat-strip"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { DATA_BASE_URL, preloadDashboard, type DashboardData } from "@/lib/data"
import { formatDate } from "@/lib/format"
import { useSeo } from "@/lib/seo"
import { PAGES } from "@/lib/seo-meta"

type ViewState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: DashboardData }

function DashboardLoading() {
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">Loading dashboard</span>
      <div className="border-b border-line bg-ivory/60 px-5 py-10 sm:px-8 lg:px-12 lg:py-16">
        <Skeleton className="h-16 w-[min(560px,82%)]" />
        <Skeleton className="mt-4 h-4 w-[min(420px,70%)]" />
        <Skeleton className="mt-3 h-4 w-[min(340px,55%)]" />
      </div>
      <div className="mx-auto max-w-375 px-5 pt-6 sm:px-8 lg:px-12">
        <div className="grid grid-cols-2 border-y border-line sm:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="px-5 py-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="mt-3 h-8 w-28" />
            </div>
          ))}
        </div>
        <div className="mt-6 grid gap-6 xl:grid-cols-12">
          <Skeleton className="h-105 w-full xl:col-span-12" />
          <Skeleton className="h-105 w-full xl:col-span-5" />
          <Skeleton className="h-105 w-full xl:col-span-7" />
        </div>
      </div>
    </div>
  )
}

function DashboardError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-5 py-16">
      <div className="w-full max-w-2xl rounded-lg border border-line bg-paper/90 px-8 py-10">
        <p className="font-serif text-3xl leading-tight text-navy">Snapshot Unavailable</p>
        <p className="mt-3 font-serif text-sm leading-relaxed text-ink/70 wrap-break-word">{message}</p>
        <div className="mt-6 space-y-2 rounded-md bg-pale/55 px-4 py-3 text-[12px] text-muted-ink">
          <p>
            Data base URL: <code>{DATA_BASE_URL || "VITE_DATA_BASE_URL is not set"}</code>
          </p>
          <p>
            Check that the pipeline wrote the snapshot. <code>R2_PUBLIC_BUCKET</code> is required.
            Confirm that <code>manifest.json</code> opens as JSON in a browser, and that the Vercel
            environment variable was set before the build.
          </p>
        </div>
        <Button onClick={onRetry} className="mt-6">
          Try Again
        </Button>
      </div>
    </div>
  )
}

export function DashboardPage() {
  useSeo(PAGES.home)
  const [state, setState] = useState<ViewState>({ status: "loading" })
  const [reloadToken, setReloadToken] = useState(0)
  const location = useLocation()

  useEffect(() => {
    let cancelled = false
    preloadDashboard(reloadToken > 0)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Unknown error",
        })
      })
    return () => {
      cancelled = true
    }
  }, [reloadToken])

  useEffect(() => {
    if (state.status !== "ready" || !location.hash) return
    const element = document.getElementById(location.hash.slice(1))
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }, [location.hash, state.status])

  const retry = () => {
    setState({ status: "loading" })
    setReloadToken((token) => token + 1)
  }

  if (state.status === "loading") return <DashboardLoading />
  if (state.status === "error") {
    return <DashboardError message={state.message} onRetry={retry} />
  }

  const { data } = state

  return (
    <>
      <EditorialHeader manifest={data.manifest} freshness={data.freshness} />

      <main className="mx-auto max-w-375 px-5 pb-16 pt-6 sm:px-8 lg:px-12">
        <StatStrip monthly={data.monthly} />

        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-12">
          <SectionCard
            id="monetary"
            index="01"
            title="Monetary Policy & Rate Corridor"
            subtitle="The policy rate and the standing-facility corridor around it."
            meta={"2017\u20132026"}
            className="xl:col-span-12"
          >
            <MonetaryChart data={data.monetary} />
          </SectionCard>

          <SectionCard
            id="liquidity"
            index="02"
            title="Liquidity"
            subtitle="M1 and M2 growth, plus the mix of broad money."
            meta={"2017\u20132026"}
            className="xl:col-span-5"
          >
            <LiquidityCard data={data.liquidity} />
          </SectionCard>

          <SectionCard
            id="inflation"
            index="03"
            title="Inflation"
            subtitle="Year-on-year headline inflation, built from BPS monthly changes."
            meta={"2017\u20132026"}
            className="xl:col-span-7"
          >
            <InflationCard data={data.monthly} />
          </SectionCard>

          <SectionCard
            id="rupiah"
            index="04"
            title="Rupiah"
            subtitle="Daily and monthly reference rates against the US dollar."
            meta={"2017\u20132026"}
            className="xl:col-span-12"
          >
            <RupiahCard data={data.rupiah} />
          </SectionCard>

          <SectionCard
            id="fiscal"
            index="05"
            title="Fiscal"
            subtitle="Budget execution and the stock of government securities."
            meta={"2017\u20132025"}
            className="xl:col-span-12"
          >
            <FiscalCard annual={data.fiscalAnnual} sbn={data.sbn} />
          </SectionCard>

          <SectionCard
            id="banking"
            index="06"
            title="Banking System Health"
            subtitle="Capital, profit, lending, and loan quality."
            meta="Latest vs Prior Month"
            className="xl:col-span-5"
          >
            <BankingTable data={data.monthly} />
          </SectionCard>

          <SectionCard
            id="credit"
            index="07"
            title="Credit Allocation"
            subtitle="How bank credit splits across economic sectors."
            meta="Latest Month"
            className="xl:col-span-7"
          >
            <CreditCard data={data.creditSector} />
          </SectionCard>

          <SectionCard
            id="regional"
            index="08"
            title="Regional Comparison"
            subtitle="Indonesia beside five regional peers, all on a YoY basis."
            meta={"2017\u20132024"}
            className="xl:col-span-12"
          >
            <RegionalCard data={data.regional} />
          </SectionCard>
        </div>

        <footer className="mt-10 border-t border-line pt-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="font-serif text-lg text-navy">Indonesia Financial Overview</p>
              <p className="mt-1 max-w-xl font-serif text-[12px] leading-relaxed text-muted-ink">
                Official statistics from Bank Indonesia, BPS, and OJK, cleaned through the
                Bronze-Silver-Gold pipeline. Unpublished months stay blank instead of zero, and
                revisions stay in the record.
              </p>
            </div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-ink">
              <p>Snapshot {formatDate(data.manifest.generated_at)}</p>
              <SocialLinks className="mt-3" />
            </div>
          </div>
        </footer>
      </main>
    </>
  )
}
