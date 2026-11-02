import { useEffect, useState } from "react"

import { SocialLinks } from "@/components/social-links"
import { useSeo } from "@/lib/seo"
import { PAGES } from "@/lib/seo-meta"
import { cn } from "@/lib/utils"

type GuideSection = {
  id: string
  index: string
  title: string
  subtitle: string
  intro: string
  example: string
  see: string[]
  read: string[]
  remember: string
}

const QUICK_QUESTIONS = [
  {
    question: "Are interest rates high right now?",
    answer:
      "The Policy Rate is the one interest rate Bank Indonesia sets. It works like the wholesale price of money: banks build their own prices on top of it. When it goes up, loans usually cost more and savings usually pay more.",
    section: "monetary",
  },
  {
    question: "Are prices rising quickly?",
    answer:
      "Inflation is the speed at which prices change. A 3% reading means the basket of things a household buys costs 3% more than a year ago. A Rp100 snack that kept pace would now cost about Rp103.",
    section: "inflation",
  },
  {
    question: "Is the rupiah stable?",
    answer:
      "USD/IDR is the price of one US dollar in rupiah. Think of a see-saw: when the number goes up, the dollar got more expensive and the rupiah buys less. When it goes down, the rupiah got stronger.",
    section: "rupiah",
  },
  {
    question: "Is the government borrowing more?",
    answer:
      "Fiscal is the government's household budget. Income comes from taxes, spending goes to roads, salaries, and subsidies. When spending is bigger than income, the gap is a deficit, and the government covers it by selling bonds.",
    section: "fiscal",
  },
  {
    question: "How are the banks doing?",
    answer:
      "Banking shows four health scores. NPL is the share of loans that stopped being paid. CAR is the safety cushion of capital. ROA is the profit squeezed from what the bank owns. LDR is how much of the deposits get lent out.",
    section: "banking",
  },
]

const GUIDE_SECTIONS: GuideSection[] = [
  {
    id: "monetary",
    index: "01",
    title: "Interest Rates",
    subtitle: "Monetary policy and the rate corridor",
    intro:
      "Bank Indonesia sets one main interest rate, the policy rate. Think of it as the wholesale price of money. Banks borrow and lend to each other near this price, then add their own markup when they deal with you. A higher rate makes borrowing more expensive and saving more rewarding.",
    example:
      "Picture a market where the central bank sets the wholesale price of money. Banks buy there and resell to customers. When the wholesale price goes up, shop prices usually follow, just not on the same day.",
    see: [
      "The thick navy line is the policy rate.",
      "The dashed teal and orange lines are the floor and ceiling around it. Together they form the corridor, a lane that keeps short-term borrowing costs inside a range.",
      "The pale blue band is that lane.",
    ],
    read: [
      "Navy line up: borrowing money costs more.",
      "Navy line down: borrowing money costs less.",
      "A wider band: banks have more room to move before hitting a limit.",
    ],
    remember:
      "Your mortgage or credit card rate will not move on the same day as the policy rate. Banks adjust over weeks or months. The July 2022 mark is only a change in which series BI reports, not a change in policy.",
  },
  {
    id: "liquidity",
    index: "02",
    title: "Money in Circulation",
    subtitle: "Liquidity, M1, and M2",
    intro:
      "Liquidity is how much money is available to spend. Think of every wallet, e-wallet, and bank account in the country as one big pool. The dashboard splits that pool into two buckets, M1 and M2.",
    example:
      "Your wallet and your spending account are M1: money you can use right now. Your savings account and a term deposit are the extra part of M2: money that exists but is parked for later.",
    see: [
      "M1 is cash in hand plus checking accounts, the money ready to spend today.",
      "M2 is M1 plus savings and time deposits, the money parked for a while.",
      "The small bars below show M1 as a share of M2: how much of the pool sits in the quick-to-spend bucket.",
    ],
    read: [
      "M2 up: the total pool of money is growing.",
      "M1's share up: more of that money sits where it can be spent right away.",
      "M1's share down: more money is parked in savings instead.",
    ],
    remember:
      "These lines count money, not prices. More money in the pool can show up alongside rising, falling, or flat prices.",
  },
  {
    id: "inflation",
    index: "03",
    title: "Inflation",
    subtitle: "The speed of price changes",
    intro:
      "The bars measure how fast average prices change across a basket of things households buy: rice, fuel, phone data, rent.",
    example:
      "If that basket cost Rp1,000,000 last year and inflation is 3%, the same basket costs about Rp1,030,000 this year.",
    see: [
      "The navy bars show year-on-year inflation: this month compared with the same month last year.",
      "The navy box in the top right shows the newest number and which month it belongs to.",
      "A bar at 0% means prices did not change. Bars above it mean prices rose; bars below it mean prices fell on average.",
    ],
    read: [
      "3%: prices are 3% higher than a year ago.",
      "A taller bar: prices are climbing faster than in the previous month.",
      "A bar below zero: prices are falling on average.",
      "A flat stretch near zero: prices are barely moving.",
    ],
    remember:
      "Inflation is an average. Your favorite snack might get cheaper while other things get pricier.",
  },
  {
    id: "rupiah",
    index: "04",
    title: "The Rupiah",
    subtitle: "USD/IDR, the price of a dollar",
    intro:
      "USD/IDR is the price of one US dollar in rupiah. A higher number means the dollar got more expensive, so the rupiah buys less of it.",
    example:
      "If USD/IDR moves from 15,000 to 15,500, a $100 item that used to cost Rp1,500,000 now costs Rp1,550,000.",
    see: [
      "JISDOR is Bank Indonesia's official daily reference rate. The chart keeps the last value in each month.",
      "SEKI is the monthly middle rate from Bank Indonesia's statistics.",
      "The navy boxes show the newest value for each line.",
    ],
    read: [
      "Line up: a dollar costs more rupiah, so the rupiah is weaker.",
      "Line down: a dollar costs fewer rupiah, so the rupiah is stronger.",
      "A flat line: the exchange rate is calm.",
    ],
    remember:
      "This chart follows only the rupiah against the US dollar. It says nothing about the rupiah versus the euro, yen, or Singapore dollar.",
  },
  {
    id: "fiscal",
    index: "05",
    title: "Government Budget",
    subtitle: "Fiscal: income, spending, and the gap",
    intro:
      "Fiscal covers the government's income, spending, and the gap between them. Think of a household budget where the salary is taxes and the shopping list is roads, schools, and salaries.",
    example:
      "A household earns Rp10 million and spends Rp12 million. The Rp2 million gap is a deficit, covered by borrowing.",
    see: [
      "Teal bars: government income, mostly taxes.",
      "Blue bars: government spending.",
      "Orange bars: the balance. Below zero is a deficit; above zero is a surplus.",
      "The shaded line is SBN, the pile of government bonds still outstanding: money borrowed and not yet paid back.",
    ],
    read: [
      "Blue taller than teal: spending outran income, so the period ran a deficit.",
      "SBN line up: the outstanding debt pile is growing.",
      "SBN line down: the pile is shrinking.",
    ],
    remember:
      "Budget numbers come from SEKI and get revised over time. The dashboard shows them in trillions of rupiah, so a small-looking bar is still a very large number.",
  },
  {
    id: "banking",
    index: "06",
    title: "Bank Health",
    subtitle: "Four ratios for the banking industry",
    intro:
      "Banks borrow money from savers and lend it to borrowers. Four ratios describe how that business is going, like four stats on a player card: cushion, profit, lending, and loan quality.",
    example:
      "Picture a bank with Rp100 in customer deposits. If it lends out Rp80 and keeps Rp20, its LDR is 80%. If Rp2 of that Rp80 never comes back, its NPL is 2.5%.",
    see: [
      "CAR: capital set aside compared with the risk of the loans. It is the safety cushion for losses.",
      "ROA: profit compared with total assets. It shows how hard the bank's money is working.",
      "LDR: loans compared with deposits. It shows how much of the deposited money gets lent out.",
      "NPL: the share of loans that are overdue or not being paid.",
    ],
    read: [
      "CAR up: a bigger cushion against losses.",
      "ROA up: more profit from the same assets.",
      "LDR up: a larger share of deposits is out on loan.",
      "NPL up: more loans stop being paid on time.",
    ],
    remember:
      "Each ratio is one number for the whole industry, an average. A healthy average can still hide a bank in trouble.",
  },
  {
    id: "credit",
    index: "07",
    title: "Where Loans Go",
    subtitle: "Credit allocation by sector",
    intro:
      "Credit is money banks lend to households and businesses. The chart splits the total loan book by sector, like splitting your phone's storage by app.",
    example:
      "If a bank has lent Rp1,000 trillion and Rp200 trillion went to trade, then trade's slice is 20%.",
    see: [
      "Horizontal bars show the ten sectors with the most credit.",
      "The percentage on the right is that sector's slice of all credit.",
      "The right panel shows total credit, the biggest sector, and how many sectors are reported.",
    ],
    read: [
      "Longer bar: more loans went to that sector.",
      "Bigger percentage: that sector takes a larger slice of the total.",
      "Short bars: smaller sectors, still possibly large in rupiah.",
    ],
    remember:
      "Only the top ten sectors are shown, but the percentages come from all sectors. That is why these ten do not add up to 100%.",
  },
  {
    id: "regional",
    index: "08",
    title: "Indonesia vs Neighbors",
    subtitle: "Regional comparison",
    intro:
      "This section places Indonesia beside five neighboring countries on two measures: how fast the economy is growing and how fast prices are rising.",
    example:
      "If Indonesia grows 5% and a neighbor grows 3%, Indonesia's line sits higher. That means the total size of the economy expanded faster, which is not the same as people being better off.",
    see: [
      "Left chart: GDP growth, compared with the same period a year earlier.",
      "Right chart: inflation, compared with the same period a year earlier.",
      "Each country keeps the same color in both charts, so you can follow it across.",
    ],
    read: [
      "Higher GDP line: the economy grew faster.",
      "Higher inflation line: prices rose faster.",
      "Two lines crossing: the ranking between those countries changed.",
    ],
    remember:
      "Countries measure things differently, and neighbor data ends in 2024. Both charts use the same time window so the comparison stays fair.",
  },
]

const GLOSSARY = [
  [
    "Policy Rate",
    "The main interest rate set by the central bank; the wholesale price of borrowing.",
    "The price a market sets before shops add their markup.",
  ],
  [
    "Inflation",
    "How fast average prices change over time.",
    "How quickly the price of rice changes.",
  ],
  [
    "YoY (Year-on-Year)",
    "This period compared with the same period last year.",
    "October 2026 versus October 2025.",
  ],
  [
    "MoM (Month-on-Month)",
    "This month compared with last month.",
    "October 2026 versus September 2026.",
  ],
  [
    "Liquidity",
    "How much money is available to spend in the economy.",
    "The size of the pool everyone can dip into.",
  ],
  [
    "M1",
    "Cash and checking deposits, the quickest money to spend.",
    "The money already in your wallet and spending account.",
  ],
  [
    "M2",
    "M1 plus savings and time deposits.",
    "M1 plus the money parked in savings.",
  ],
  [
    "JISDOR",
    "Bank Indonesia's daily exchange rate reference against the US dollar.",
    "The official daily price tag on one US dollar.",
  ],
  [
    "SEKI",
    "Bank Indonesia's economic statistics publication.",
    "The monthly stats book this dashboard pulls from.",
  ],
  [
    "Corridor",
    "The range between the floor and ceiling for short-term interest rates.",
    "A lane that keeps rates from drifting too far.",
  ],
  [
    "SBN",
    "Government bonds; debt the government issues and trades.",
    "An IOU the government sells to raise money.",
  ],
  [
    "APBN",
    "Indonesia's state budget: government income and spending.",
    "The government's annual household budget.",
  ],
  [
    "Deficit",
    "When spending is larger than income.",
    "Spending Rp12 million out of a Rp10 million income.",
  ],
  [
    "CAR",
    "Capital Adequacy Ratio; capital compared with risk-weighted loans.",
    "The cushion a bank keeps for a rainy day.",
  ],
  [
    "ROA",
    "Return on Assets; profit compared with assets.",
    "How much profit each rupiah of assets earns.",
  ],
  [
    "LDR",
    "Loan-to-Deposit Ratio; loans compared with deposits.",
    "Of every Rp100 deposited, how much is lent out.",
  ],
  [
    "NPL",
    "Non-Performing Loan; the share of loans not paid on time.",
    "The slice of the loan book that went bad.",
  ],
  [
    "GDP",
    "The total value of goods and services a country produces.",
    "Everything the country made and sold in a year.",
  ],
  ["bp", "Basis point; 100 bp equals 1 percentage point.", "0.25% is the same as 25 bp."],
]

const TABLE_OF_CONTENTS = [
  { id: "quick", label: "Five Quick Questions" },
  { id: "charts", label: "How to Read the Charts" },
  ...GUIDE_SECTIONS.map((section) => ({
    id: `${section.id}`,
    label: section.title,
  })),
  { id: "glossary", label: "Glossary" },
  { id: "limits", label: "Data Limits" },
]

const TOC_IDS = TABLE_OF_CONTENTS.map((item) => item.id)

function useActiveSection(ids: string[]) {
  const [activeId, setActiveId] = useState(ids[0])

  useEffect(() => {
    const sections = ids
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null)
    if (sections.length === 0) return

    const updateActive = () => {
      const offset = 120
      let currentId = sections[0].id
      for (const section of sections) {
        if (section.getBoundingClientRect().top <= offset) currentId = section.id
        else break
      }
      setActiveId(currentId)
    }

    updateActive()
    window.addEventListener("scroll", updateActive, { passive: true })
    window.addEventListener("resize", updateActive)
    return () => {
      window.removeEventListener("scroll", updateActive)
      window.removeEventListener("resize", updateActive)
    }
  }, [ids])

  return activeId
}

function GuideSection({ section }: { section: GuideSection }) {
  return (
    <section id={`${section.id}`} className="scroll-mt-24">
      <header className="border-b border-line pb-3">
        <div className="flex items-baseline gap-3">
          <span className="font-serif text-lg text-teal/70">{section.index}</span>
          <div>
            <h2 className="font-serif text-[26px] leading-tight text-navy">{section.title}</h2>
            <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-muted-ink">
              {section.subtitle}
            </p>
          </div>
        </div>
      </header>

      <p className="mt-4 font-serif text-[16px] leading-7 text-ink/85">{section.intro}</p>

      <div className="mt-4 rounded-md border border-teal/20 bg-teal/4 px-4 py-3">
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal">
          In Everyday Terms
        </h3>
        <p className="mt-1 font-serif text-[13px] leading-relaxed text-ink/75">{section.example}</p>
      </div>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <div>
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal">
            What You See
          </h3>
          <ul className="mt-2 space-y-1.5 pl-4 text-[13px] leading-relaxed text-ink/75 marker:text-teal/60 list-disc">
            {section.see.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-navy">
            How to Read It
          </h3>
          <ul className="mt-2 space-y-1.5 pl-4 text-[13px] leading-relaxed text-ink/75 marker:text-navy/50 list-disc">
            {section.read.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-4 rounded-md bg-pale/50 px-4 py-3 font-serif text-[13px] leading-relaxed text-ink/75">
        <span className="font-semibold text-navy">Remember: </span>
        {section.remember}
      </div>
    </section>
  )
}

export function GuidePage() {
  useSeo(PAGES.guide)
  const activeId = useActiveSection(TOC_IDS)

  return (
    <>
      <header className="border-b border-line bg-ivory/60">
        <div className="mx-auto max-w-275 px-5 py-10 sm:px-8 lg:px-12 lg:py-16">
          <h1 className="max-w-3xl font-serif text-[clamp(2.5rem,5.5vw,4.2rem)] leading-[0.94] tracking-[-0.04em] text-navy">
            How to Read
            <br />
            <span className="italic text-teal">this dashboard</span>
          </h1>
          <p className="mt-5 max-w-2xl font-serif text-lg leading-relaxed text-ink/75">
            This page explains the dashboard in plain words, with everyday comparisons. You do not
            need an economics background to use it.
          </p>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted-ink">
            Chart labels keep their official terms. Each section explains what a number means and
            gives a small everyday example.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-275 px-5 py-10 sm:px-8 lg:px-12 lg:py-14">
        <div className="grid gap-10 lg:grid-cols-[220px_1fr]">
          <aside className="hidden lg:block">
            <div className="sticky top-8">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-ink">
                On This Page
              </p>
              <ul className="mt-3 space-y-0.5">
                {TABLE_OF_CONTENTS.map((item) => {
                  const isActive = item.id === activeId
                  return (
                    <li key={item.id}>
                      <a
                        href={`#${item.id}`}
                        aria-current={isActive ? "location" : undefined}
                        className={cn(
                          "block border-l-2 py-1 pl-3 text-[12px] leading-snug transition-colors",
                          isActive
                            ? "border-teal font-medium text-navy"
                            : "border-line text-ink/65 hover:text-navy",
                        )}
                      >
                        {item.label}
                      </a>
                    </li>
                  )
                })}
              </ul>
            </div>
          </aside>

          <article className="min-w-0">
            <div className="space-y-12">
              <section id="quick" className="scroll-mt-24">
                <h2 className="font-serif text-[30px] leading-tight text-navy">
                  Five Quick Questions
                </h2>
                <p className="mt-3 max-w-2xl font-serif text-[15px] leading-7 text-ink/75">
                  Each question links to the section that answers it, where the idea is explained
                  again with an example.
                </p>
                <ol className="mt-6 grid gap-x-8 gap-y-6 sm:grid-cols-2">
                  {QUICK_QUESTIONS.map((item, index) => (
                    <li key={item.question} className="border-t border-line pt-3">
                      <span className="font-serif text-sm text-teal">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <p className="mt-1 font-serif text-lg leading-snug text-navy">
                        {item.question}
                      </p>
                      <p className="mt-1 text-[13px] leading-relaxed text-ink/70">{item.answer}</p>
                      <a
                        href={`#${item.section}`}
                        className="mt-2 inline-block text-[10px] uppercase tracking-[0.16em] text-teal hover:underline"
                      >
                        Read this section
                      </a>
                    </li>
                  ))}
                </ol>
              </section>

              <section id="charts" className="scroll-mt-24">
                <h2 className="font-serif text-[30px] leading-tight text-navy">
                  How to Read the Charts
                </h2>
                <p className="mt-3 max-w-2xl font-serif text-[15px] leading-7 text-ink/75">
                  Every chart is built from the same four pieces, so these four are worth knowing.
                </p>
                <dl className="mt-6 grid gap-5 sm:grid-cols-2">
                  <div className="border-t border-line pt-3">
                    <dt className="font-serif text-lg text-navy">Line</dt>
                    <dd className="mt-1 text-[13px] leading-relaxed text-ink/70">
                      A line connects values across time. Up means the number got bigger. Picture a
                      line of monthly exchange rates, one dot per month.
                    </dd>
                  </div>
                  <div className="border-t border-line pt-3">
                    <dt className="font-serif text-lg text-navy">Bar</dt>
                    <dd className="mt-1 text-[13px] leading-relaxed text-ink/70">
                      A bar shows the size of something in one period. Longer means bigger. Picture
                      one bar per month of inflation.
                    </dd>
                  </div>
                  <div className="border-t border-line pt-3">
                    <dt className="font-serif text-lg text-navy">Shaded Area</dt>
                    <dd className="mt-1 text-[13px] leading-relaxed text-ink/70">
                      A shaded area fills the gap between two lines or values, like a range. Picture
                      the band between the rate floor and ceiling.
                    </dd>
                  </div>
                  <div className="border-t border-line pt-3">
                    <dt className="font-serif text-lg text-navy">Color</dt>
                    <dd className="mt-1 text-[13px] leading-relaxed text-ink/70">
                      Navy is the main data. Teal is the second data set. Orange marks a specific
                      value. Blue is supporting data.
                    </dd>
                  </div>
                </dl>
                <p className="mt-5 rounded-md bg-pale/50 px-4 py-3 font-serif text-[13px] leading-relaxed text-ink/75">
                  Hover to see the exact number. The time axis shows years, but the data underneath
                  is monthly or quarterly. If a chart looks empty for a recent month, the source
                  simply has not published it yet; it is not zero.
                </p>
              </section>

              {GUIDE_SECTIONS.map((section) => (
                <GuideSection key={section.id} section={section} />
              ))}

              <section id="glossary" className="scroll-mt-24">
                <h2 className="font-serif text-[30px] leading-tight text-navy">Glossary</h2>
                <p className="mt-3 max-w-2xl font-serif text-[15px] leading-7 text-ink/75">
                  The terms that show up most on the dashboard, with a plain meaning and a
                  one-line picture.
                </p>
                <div className="mt-5 overflow-x-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr>
                        <th className="border-b border-line py-2 pr-6 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-ink">
                          Term
                        </th>
                        <th className="border-b border-line py-2 pr-6 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-ink">
                          Plain Meaning
                        </th>
                        <th className="border-b border-line py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-ink">
                          Everyday Picture
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {GLOSSARY.map(([term, meaning, picture]) => (
                        <tr key={term}>
                          <td className="whitespace-nowrap border-b border-line/70 py-2 pr-6 font-serif text-[14px] text-navy">
                            {term}
                          </td>
                          <td className="border-b border-line/70 py-2 pr-6 text-[13px] leading-relaxed text-ink/70">
                            {meaning}
                          </td>
                          <td className="border-b border-line/70 py-2 text-[13px] leading-relaxed text-ink/60">
                            {picture}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section id="limits" className="scroll-mt-24">
                <h2 className="font-serif text-[30px] leading-tight text-navy">Data Limits</h2>
                <p className="mt-3 max-w-2xl font-serif text-[15px] leading-7 text-ink/75">
                  What the data can and cannot show.
                </p>
                <ul className="mt-4 space-y-2 pl-4 text-[13px] leading-relaxed text-ink/75 marker:text-teal/60 list-disc">
                  <li>It shows past and current data. It does not predict the future.</li>
                  <li>It is not investment advice.</li>
                  <li>Official data can be revised. The newest number might change.</li>
                  <li>
                    It is not live. The sidebar shows when the latest snapshot was taken.
                  </li>
                  <li>A month with no published data is left blank, not filled with zero.</li>
                  <li>
                    An industry total mixes all banks together. It hides differences between
                    banks, regions, and households.
                  </li>
                  <li>
                    A strong or weak reading is not good or bad by itself. It depends on what you
                    are comparing it with.
                  </li>
                </ul>
              </section>
            </div>

            <footer className="mt-12 border-t border-line pt-6">
              <p className="max-w-xl font-serif text-[12px] leading-relaxed text-muted-ink">
                Sources: Bank Indonesia (SEKI and JISDOR), BPS, and OJK. Educational use only; not
                financial advice.
              </p>
              <SocialLinks className="mt-3" />
            </footer>
          </article>
        </div>
      </main>
    </>
  )
}
