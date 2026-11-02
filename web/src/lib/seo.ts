import { useEffect } from "react"

import { OG_IMAGE_ALT, OG_IMAGE_PATH, SITE_NAME, type PageMeta } from "@/lib/seo-meta"

const configuredSiteUrl = import.meta.env.VITE_SITE_URL?.replace(/\/+$/, "")

function siteOrigin(): string {
  return configuredSiteUrl || window.location.origin
}

function absoluteUrl(path: string): string {
  return `${siteOrigin()}${path}`
}

function setMeta(key: string, content: string, attribute: "name" | "property" = "name"): void {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`)
  if (!element) {
    element = document.createElement("meta")
    element.setAttribute(attribute, key)
    document.head.append(element)
  }
  element.content = content
}

function setLink(rel: string, href: string): void {
  let element = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`)
  if (!element) {
    element = document.createElement("link")
    element.rel = rel
    document.head.append(element)
  }
  element.href = href
}

export function useSeo(page: PageMeta): void {
  useEffect(() => {
    const url = absoluteUrl(page.path)
    const image = absoluteUrl(OG_IMAGE_PATH)

    document.title = page.title
    setMeta("description", page.description)
    setMeta("robots", "index, follow, max-image-preview:large, max-snippet:-1")
    setLink("canonical", url)

    setMeta("og:site_name", SITE_NAME, "property")
    setMeta("og:type", "website", "property")
    setMeta("og:title", page.title, "property")
    setMeta("og:description", page.description, "property")
    setMeta("og:url", url, "property")
    setMeta("og:image", image, "property")
    setMeta("og:image:type", "image/png", "property")
    setMeta("og:image:width", "1200", "property")
    setMeta("og:image:height", "630", "property")
    setMeta("og:image:alt", OG_IMAGE_ALT, "property")

    setMeta("twitter:card", "summary_large_image")
    setMeta("twitter:title", page.title)
    setMeta("twitter:description", page.description)
    setMeta("twitter:image", image)
    setMeta("twitter:image:alt", OG_IMAGE_ALT)
  }, [page])
}
