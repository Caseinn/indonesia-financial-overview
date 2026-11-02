export const SITE_NAME = "Indonesia Financial Overview"

export const DEFAULT_TITLE = "Indonesia Financial Overview — Official Macro Data"

export const DEFAULT_DESCRIPTION =
  "Monthly official data on Indonesia's policy rate, money supply, inflation, rupiah, fiscal position, and banks, from Bank Indonesia, BPS, and OJK."

export const DATA_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

export const OG_IMAGE_PATH = "/og.png"

export const OG_IMAGE_ALT =
  "Indonesia Financial Overview masthead with the Jakarta skyline and a rising bar chart"

export type PageMeta = {
  path: string
  title: string
  description: string
  changeFrequency: "weekly" | "monthly"
  priority: string
}

export const PAGES = {
  home: {
    path: "/",
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
    changeFrequency: "weekly",
    priority: "1.0",
  },
  guide: {
    path: "/guide",
    title: "Reading Guide — Indonesia Financial Overview",
    description:
      "A plain-language guide to Indonesia's key economic indicators: interest rates, money supply, inflation, the rupiah, fiscal balance, and bank health.",
    changeFrequency: "monthly",
    priority: "0.6",
  },
} satisfies Record<string, PageMeta>
