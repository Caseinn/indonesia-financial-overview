import { useEffect, useState } from "react"
import { Outlet } from "react-router-dom"

import { MobileSidebar, Sidebar } from "@/components/sidebar"
import { preloadLayout, type LayoutData } from "@/lib/data"

export function SiteShell() {
  const [layout, setLayout] = useState<LayoutData | null>(null)

  useEffect(() => {
    let cancelled = false
    preloadLayout()
      .then((data) => {
        if (!cancelled) setLayout(data)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="min-h-screen">
      <MobileSidebar freshness={layout?.freshness} manifest={layout?.manifest} />
      <Sidebar freshness={layout?.freshness} manifest={layout?.manifest} />
      <div className="lg:pl-70">
        <Outlet />
      </div>
    </div>
  )
}
