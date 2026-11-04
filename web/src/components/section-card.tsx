import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type SectionCardProps = {
  id: string
  index: string
  title: string
  subtitle?: string
  meta?: ReactNode
  children: ReactNode
  className?: string
}

export function SectionCard({
  id,
  index,
  title,
  subtitle,
  meta,
  children,
  className,
}: SectionCardProps) {
  return (
    <section
      id={id}
      data-section={id}
      className={cn(
        "scroll-mt-24 overflow-hidden rounded-lg border border-line bg-background shadow-[0_1px_0_rgba(20,42,54,0.04)]",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line/80 px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="pt-0.5 font-serif text-lg leading-none text-teal/70">{index}</span>
          <div>
            <h2 className="font-sans text-xs font-semibold uppercase tracking-[0.2em] text-navy">
              {title}
            </h2>
            {subtitle ? (
              <p className="mt-1 max-w-2xl font-serif text-sm leading-snug text-muted-ink">
                {subtitle}
              </p>
            ) : null}
          </div>
        </div>
        {meta ? (
          <div className="pt-0.5 text-[10px] uppercase tracking-[0.16em] text-muted-ink">
            {meta}
          </div>
        ) : null}
      </header>
      <div className="px-5 py-5">{children}</div>
    </section>
  )
}
