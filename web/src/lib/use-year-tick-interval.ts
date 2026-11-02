import { useEffect, useRef, useState } from "react"

import { POINTS_PER_YEAR, yearTickInterval } from "@/lib/charting"

const INITIAL_WIDTH = 320

export function useYearTickInterval(
  pointCount: number,
  pointsPerYear: number = POINTS_PER_YEAR.monthly,
) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(INITIAL_WIDTH)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(entry.contentRect.width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return [ref, yearTickInterval(pointCount, width, pointsPerYear)] as const
}
