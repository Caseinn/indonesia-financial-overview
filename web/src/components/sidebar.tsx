import { ArrowLeft, BookOpen, List, X } from "@phosphor-icons/react"
import { useState } from "react"
import { Link, useLocation } from "react-router-dom"

import { StatusDot } from "@/components/status-dot"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import type { FreshnessRow, Manifest } from "@/lib/data"
import { formatDate } from "@/lib/format"
import { SECTIONS } from "@/lib/sections"

type SidebarProps = {
  freshness?: FreshnessRow[]
  manifest?: Manifest
}

type SidebarContentProps = SidebarProps & {
  onDismiss?: () => void
}

function SidebarContent({ freshness, manifest, onDismiss }: SidebarContentProps) {
  const { pathname } = useLocation()
  const isGuide = pathname === "/guide"
  const healthy = freshness?.[0]?.global_healthy ?? false
  const stale = freshness?.filter((row) => !row.is_fresh) ?? []

  return (
    <div className="relative flex h-full flex-col">
      <div className="border-b border-sidebar-border/60 px-6 py-6">
        {onDismiss ? (
          <button
            type="button"
            aria-label="Close sections"
            onClick={onDismiss}
            className="absolute right-4 top-5 rounded-md p-1 text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
          >
            <X className="size-4" />
          </button>
        ) : null}
        <p className="font-serif text-[26px] leading-[1.05] tracking-[-0.01em]">
          Indonesia
          <br />
          <span className="italic text-sidebar-primary">Financial Overview</span>
        </p>
        <p className="mt-3 text-[10px] uppercase tracking-[0.22em] text-sidebar-foreground/65">
          Official Statistics Reader
        </p>
      </div>

      <nav aria-label="Dashboard sections" className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="flex flex-col gap-0.5">
          {SECTIONS.map((section) => {
            const Icon = section.icon
            return (
              <li key={section.id}>
                <Link
                  to={`/#${section.id}`}
                  onClick={onDismiss}
                  className="group flex items-start gap-3 rounded-md px-3 py-2 text-sidebar-foreground/85 transition-colors hover:bg-sidebar-accent/60"
                >
                  <span className="pt-0.5 font-serif text-sm tabular-nums text-sidebar-primary/80">
                    {section.index}
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 font-serif text-[15px] leading-tight">
                      <Icon
                        className="size-4 shrink-0 text-sidebar-foreground/70"
                        weight="light"
                      />
                      {section.title}
                    </span>
                    <span className="mt-1 block text-[11px] leading-snug text-sidebar-foreground/65">
                      {section.description}
                    </span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {manifest ? (
        <div className="border-t border-sidebar-border/60 px-6 py-4">
          <div className="flex items-center gap-2">
            <StatusDot healthy={healthy} />
            <p className="text-[10px] uppercase tracking-[0.18em] text-sidebar-foreground/70">
              {healthy ? "All sources fresh" : "Source lag detected"}
            </p>
          </div>
          {stale.length > 0 ? (
            <p className="mt-1.5 text-[11px] leading-snug text-orange-soft">
              {stale.map((row) => row.source_id).join(", ")}
            </p>
          ) : null}
          <p className="mt-2 font-serif text-[11px] text-sidebar-foreground/60">
            Snapshot {formatDate(manifest.generated_at)}
          </p>
        </div>
      ) : null}

      <div className="border-t border-sidebar-border/60 px-3 py-3">
        <Link
          to={isGuide ? "/" : "/guide"}
          onClick={onDismiss}
          className="group flex items-start gap-3 rounded-md px-3 py-2 text-sidebar-foreground/85 transition-colors hover:bg-sidebar-accent/60"
        >
          <span className="min-w-0">
            <span className="flex items-center gap-2 font-serif text-[15px] leading-tight">
              {isGuide ? (
                <ArrowLeft className="size-4 shrink-0 text-sidebar-foreground/70" weight="light" />
              ) : (
                <BookOpen className="size-4 shrink-0 text-sidebar-foreground/70" weight="light" />
              )}
              {isGuide ? "Back to Dashboard" : "Reading Guide"}
            </span>
            <span className="mt-1 block text-[11px] leading-snug text-sidebar-foreground/65">
              {isGuide ? "Return to the charts" : "For non-economists"}
            </span>
          </span>
        </Link>
      </div>
    </div>
  )
}

export function Sidebar({ freshness, manifest }: SidebarProps) {
  return (
    <aside className="hidden bg-teal-deep text-sidebar-foreground lg:fixed lg:inset-y-0 lg:left-0 lg:z-40 lg:block lg:w-70">
      <SidebarContent freshness={freshness} manifest={manifest} />
    </aside>
  )
}

export function MobileSidebar({ freshness, manifest }: SidebarProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-background/95 px-4 py-3 backdrop-blur lg:hidden">
      <Link to="/" className="font-serif text-lg leading-tight text-navy">
        Indonesia <span className="italic text-teal">Financial Overview</span>
      </Link>
      <Button
        variant="outline"
        size="icon"
        aria-label="Open sections"
        onClick={() => setOpen(true)}
        className="border-line bg-paper text-navy"
      >
        <List className="size-4" />
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="left"
          showCloseButton={false}
          className="w-75 max-w-[86vw] border-sidebar-border bg-teal-deep p-0 text-sidebar-foreground"
        >
          <SheetTitle className="sr-only">Dashboard Sections</SheetTitle>
          <SidebarContent
            freshness={freshness}
            manifest={manifest}
            onDismiss={() => setOpen(false)}
          />
        </SheetContent>
      </Sheet>
    </div>
  )
}
