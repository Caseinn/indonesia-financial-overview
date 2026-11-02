import { GithubLogo, InstagramLogo, LinkedinLogo } from "@phosphor-icons/react"

import { cn } from "@/lib/utils"

const SOCIAL_LINKS = [
  { href: "https://github.com/caseinn", label: "GitHub", Icon: GithubLogo },
  { href: "https://instagram.com/ditorifkii", label: "Instagram", Icon: InstagramLogo },
  { href: "https://linkedin.com/in/ditorifki", label: "LinkedIn", Icon: LinkedinLogo },
] as const

export function SocialLinks({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-end gap-1", className)}>
      {SOCIAL_LINKS.map(({ href, label, Icon }) => (
        <a
          key={label}
          href={href}
          target="_blank"
          rel="noreferrer"
          aria-label={label}
          className="rounded-md p-1.5 text-muted-ink transition-colors hover:bg-pale hover:text-navy"
        >
          <Icon className="size-5" weight="light" />
        </a>
      ))}
    </div>
  )
}
