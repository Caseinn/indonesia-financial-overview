import {
  Bank,
  Briefcase,
  Buildings,
  CurrencyCircleDollar,
  Drop,
  Globe,
  TrendUp,
} from "@phosphor-icons/react"

export const SECTIONS = [
  {
    id: "monetary",
    index: "01",
    title: "Monetary Policy",
    description: "Policy rate and the corridor",
    icon: Bank,
  },
  {
    id: "liquidity",
    index: "02",
    title: "Liquidity",
    description: "Money supply and composition",
    icon: Drop,
  },
  {
    id: "inflation",
    index: "03",
    title: "Inflation",
    description: "Headline inflation since 2017",
    icon: TrendUp,
  },
  {
    id: "rupiah",
    index: "04",
    title: "Rupiah",
    description: "JISDOR and SEKI reference rates",
    icon: CurrencyCircleDollar,
  },
  {
    id: "fiscal",
    index: "05",
    title: "Fiscal",
    description: "Budget balance and SBN stock",
    icon: Bank,
  },
  {
    id: "banking",
    index: "06",
    title: "Banking System Health",
    description: "Capital, earnings, and credit quality",
    icon: Buildings,
  },
  {
    id: "credit",
    index: "07",
    title: "Credit Allocation",
    description: "Lending by economic sector",
    icon: Briefcase,
  },
  {
    id: "regional",
    index: "08",
    title: "Regional Comparison",
    description: "Growth and prices across peers",
    icon: Globe,
  },
] as const
