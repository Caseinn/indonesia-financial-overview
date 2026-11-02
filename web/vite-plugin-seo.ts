import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import type { HtmlTagDescriptor, Plugin } from "vite"

import {
  DATA_LICENSE_URL,
  DEFAULT_DESCRIPTION,
  DEFAULT_TITLE,
  OG_IMAGE_ALT,
  OG_IMAGE_PATH,
  PAGES,
  SITE_NAME,
  type PageMeta,
} from "./src/lib/seo-meta.ts"

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;")
}

function replaceAttribute(html: string, pattern: RegExp, value: string): string {
  return html.replace(
    pattern,
    (_match: string, before: string, after: string) => `${before}${escapeXml(value)}${after}`,
  )
}

function replacePageMeta(html: string, page: PageMeta, siteUrl: string): string {
  const url = page.path === "/" ? `${siteUrl}/` : `${siteUrl}${page.path}`

  let result = html.replace(
    /<title>[\s\S]*?<\/title>/,
    `<title>${escapeXml(page.title)}</title>`,
  )
  result = replaceAttribute(
    result,
    /(<meta\s+name="description"[\s\S]*?content=")[^"]*(")/,
    page.description,
  )
  result = replaceAttribute(result, /(<link rel="canonical" href=")[^"]*(")/, url)
  result = replaceAttribute(
    result,
    /(<link rel="alternate" hreflang="en" href=")[^"]*(")/,
    url,
  )
  result = replaceAttribute(
    result,
    /(<link rel="alternate" hreflang="x-default" href=")[^"]*(")/,
    url,
  )
  result = replaceAttribute(
    result,
    /(<meta property="og:title" content=")[^"]*(")/,
    page.title,
  )
  result = replaceAttribute(
    result,
    /(<meta property="og:description" content=")[^"]*(")/,
    page.description,
  )
  result = replaceAttribute(result, /(<meta property="og:url" content=")[^"]*(")/, url)
  result = replaceAttribute(
    result,
    /(<meta name="twitter:title" content=")[^"]*(")/,
    page.title,
  )
  result = replaceAttribute(
    result,
    /(<meta name="twitter:description" content=")[^"]*(")/,
    page.description,
  )
  return result
}

function structuredData(siteUrl: string): string {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${siteUrl}/#website`,
        url: `${siteUrl}/`,
        name: SITE_NAME,
        description: DEFAULT_DESCRIPTION,
        inLanguage: "en",
        publisher: { "@type": "Organization", name: SITE_NAME, url: `${siteUrl}/` },
      },
      {
        "@type": "Dataset",
        "@id": `${siteUrl}/#dataset`,
        name: "Indonesia macroeconomic and financial indicators",
        description: DEFAULT_DESCRIPTION,
        url: `${siteUrl}/`,
        isAccessibleForFree: true,
        license: DATA_LICENSE_URL,
        spatialCoverage: { "@type": "Place", name: "Indonesia" },
        temporalCoverage: "2017/..",
        creator: { "@type": "Organization", name: SITE_NAME, url: `${siteUrl}/` },
        variableMeasured: [
          "Policy rate",
          "Broad money (M2)",
          "Headline inflation",
          "USD/IDR reference rate",
          "Fiscal balance",
          "Government securities outstanding",
          "Bank capital adequacy",
          "Non-performing loans",
          "Credit by economic sector",
          "Regional growth",
        ],
      },
    ],
  })
}

/**
 * Injects canonical, Open Graph, Twitter, and Dataset metadata into the built
 * HTML, and writes robots.txt plus sitemap.xml from VITE_SITE_URL.
 */
export function seoPlugin(siteUrl: string): Plugin {
  const normalized = siteUrl.replace(/\/+$/, "")
  let outDir = "dist"
  let isBuild = false

  return {
    name: "seo",
    configResolved(config) {
      outDir = config.build.outDir
      isBuild = config.command === "build"
    },
    transformIndexHtml(): HtmlTagDescriptor[] {
      const license: HtmlTagDescriptor = {
        tag: "link",
        attrs: { rel: "license", href: DATA_LICENSE_URL },
        injectTo: "head",
      }
      if (!normalized) return [license]

      const page = PAGES.home
      const url = `${normalized}${page.path}`
      const image = `${normalized}${OG_IMAGE_PATH}`

      return [
        license,
        { tag: "link", attrs: { rel: "canonical", href: url }, injectTo: "head" },
        {
          tag: "link",
          attrs: { rel: "alternate", hreflang: "en", href: url },
          injectTo: "head",
        },
        {
          tag: "link",
          attrs: { rel: "alternate", hreflang: "x-default", href: url },
          injectTo: "head",
        },
        { tag: "meta", attrs: { property: "og:type", content: "website" }, injectTo: "head" },
        { tag: "meta", attrs: { property: "og:site_name", content: SITE_NAME }, injectTo: "head" },
        { tag: "meta", attrs: { property: "og:locale", content: "en_US" }, injectTo: "head" },
        { tag: "meta", attrs: { property: "og:title", content: DEFAULT_TITLE }, injectTo: "head" },
        {
          tag: "meta",
          attrs: { property: "og:description", content: DEFAULT_DESCRIPTION },
          injectTo: "head",
        },
        { tag: "meta", attrs: { property: "og:url", content: url }, injectTo: "head" },
        { tag: "meta", attrs: { property: "og:image", content: image }, injectTo: "head" },
        {
          tag: "meta",
          attrs: { property: "og:image:type", content: "image/png" },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { property: "og:image:width", content: "1200" },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { property: "og:image:height", content: "630" },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { property: "og:image:alt", content: OG_IMAGE_ALT },
          injectTo: "head",
        },
        {
          tag: "meta",
          attrs: { name: "twitter:card", content: "summary_large_image" },
          injectTo: "head",
        },
        { tag: "meta", attrs: { name: "twitter:title", content: DEFAULT_TITLE }, injectTo: "head" },
        {
          tag: "meta",
          attrs: { name: "twitter:description", content: DEFAULT_DESCRIPTION },
          injectTo: "head",
        },
        { tag: "meta", attrs: { name: "twitter:image", content: image }, injectTo: "head" },
        {
          tag: "meta",
          attrs: { name: "twitter:image:alt", content: OG_IMAGE_ALT },
          injectTo: "head",
        },
        {
          tag: "script",
          attrs: { type: "application/ld+json" },
          children: structuredData(normalized),
          injectTo: "head",
        },
      ]
    },
    closeBundle() {
      if (!isBuild) return

      const directory = resolve(outDir)
      mkdirSync(directory, { recursive: true })

      const robotsLines = ["User-agent: *", "Allow: /", ""]
      if (normalized) robotsLines.push(`Sitemap: ${normalized}/sitemap.xml`)
      writeFileSync(resolve(directory, "robots.txt"), `${robotsLines.join("\n")}\n`, "utf8")

      const indexHtml = readFileSync(resolve(directory, "index.html"), "utf8")
      writeFileSync(
        resolve(directory, "guide.html"),
        replacePageMeta(indexHtml, PAGES.guide, normalized),
        "utf8",
      )

      if (!normalized) {
        this.warn("No site URL available; skipped sitemap.xml and URL-based metadata")
        return
      }

      const lastmod = new Date().toISOString().slice(0, 10)
      const urls = Object.values(PAGES)
        .map((page) => {
          const loc = page.path === "/" ? `${normalized}/` : `${normalized}${page.path}`
          return [
            "  <url>",
            `    <loc>${escapeXml(loc)}</loc>`,
            `    <lastmod>${lastmod}</lastmod>`,
            `    <changefreq>${page.changeFrequency}</changefreq>`,
            `    <priority>${page.priority}</priority>`,
            "  </url>",
          ].join("\n")
        })
        .join("\n")

      const sitemap = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        urls,
        "</urlset>",
        "",
      ].join("\n")

      writeFileSync(resolve(directory, "sitemap.xml"), sitemap, "utf8")
    },
  }
}
