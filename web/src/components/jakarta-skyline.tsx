type JakartaSkylineProps = {
  className?: string
}

export function JakartaSkyline({ className }: JakartaSkylineProps) {
  return (
    <img
      src="/jakarta-skyline.webp"
      alt=""
      aria-hidden="true"
      fetchPriority="high"
      decoding="async"
      className={className}
    />
  )
}
