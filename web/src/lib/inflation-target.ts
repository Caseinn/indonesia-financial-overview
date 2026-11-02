export type InflationTargetEra = {
  start: string
  end: string
  target: number
  corridor: number
  label: string
}

export const INFLATION_TARGET_ERAS: InflationTargetEra[] = [
  { start: "2017-01-01", end: "2017-12-01", target: 4, corridor: 1, label: "4±1%" },
  { start: "2018-01-01", end: "2019-12-01", target: 3.5, corridor: 1, label: "3.5±1%" },
  { start: "2020-01-01", end: "2023-12-01", target: 3, corridor: 1, label: "3±1%" },
  { start: "2024-01-01", end: "2027-12-01", target: 2.5, corridor: 1, label: "2.5±1%" },
]
