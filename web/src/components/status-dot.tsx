import { cn } from "@/lib/utils"

type StatusDotProps = {
  healthy: boolean
  className?: string
}

export function StatusDot({ healthy, className }: StatusDotProps) {
  const color = healthy ? "bg-emerald-300" : "bg-orange-soft"

  return (
    <span
      className={cn("relative inline-flex size-2 items-center justify-center", className)}
      aria-hidden="true"
    >
      <span className={cn("status-pulse-ring absolute inset-0 rounded-full", color)} />
      <span
        className={cn("status-pulse-ring-delayed absolute inset-0 rounded-full", color)}
      />
      <span className={cn("status-pulse-core relative size-2 rounded-full", color)} />
    </span>
  )
}
