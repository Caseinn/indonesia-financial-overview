import { JakartaSkyline } from "@/components/jakarta-skyline"
import type { FreshnessRow, Manifest } from "@/lib/data"
import { formatDate } from "@/lib/format"

type EditorialHeaderProps = {
  manifest: Manifest
  freshness: FreshnessRow[]
}

export function EditorialHeader({ manifest, freshness }: EditorialHeaderProps) {
  const healthy = freshness[0]?.global_healthy ?? false

  return (
    <header className="relative overflow-hidden border-b border-line bg-ivory/60">
      <JakartaSkyline className="pointer-events-none absolute right-0 top-0 h-full w-[68%] opacity-40 mask-[linear-gradient(to_left,black_48%,transparent)] sm:w-[60%] lg:opacity-95" />
      <div className="relative mx-auto max-w-375 px-5 py-10 sm:px-8 lg:px-12 lg:py-16">
        <div className="max-w-3xl">
          <h1 className="font-serif text-[clamp(2.7rem,6.2vw,5.4rem)] leading-[0.92] tracking-[-0.04em] text-navy">
            Indonesia
            <br />
            <span className="italic text-teal">Financial Overview</span>
          </h1>
          <p className="mt-6 max-w-xl font-serif text-lg leading-relaxed text-ink/75">
            Monthly official data on monetary policy, liquidity, prices, the rupiah, fiscal
            capacity, and the banking system.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2 text-[10px] uppercase tracking-[0.2em] text-muted-ink">
            <span>Bank Indonesia</span>
            <span className="text-line">&middot;</span>
            <span>BPS</span>
            <span className="text-line">&middot;</span>
            <span>OJK</span>
            <span className="text-line">&middot;</span>
            <span className="text-navy">Updated {formatDate(manifest.generated_at)}</span>
            <span className="text-line">&middot;</span>
            <span className={healthy ? "text-teal" : "text-orange"}>
              {healthy ? "All sources fresh" : "Source lag detected"}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}
