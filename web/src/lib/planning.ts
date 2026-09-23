import type { PlanningMonthItem } from './planningTypes'

export type LaneMeta = { color: string; label: string; purpose: string }

export const LANE_META: Record<string, LaneMeta> = {
  product: {
    color: 'var(--color-lane-product)',
    label: "PRODUCT · Why It's Here",
    purpose: 'Keeps real stock visible and sellable.',
  },
  fitting: {
    color: 'var(--color-lane-fitting)',
    label: 'FITTING · Fit First',
    purpose: 'Builds demand for custom fitting.',
  },
  coaching: {
    color: 'var(--color-lane-coaching)',
    label: 'COACHING · Ask Stick',
    purpose: 'Shows expertise + improvement.',
  },
  workshop: {
    color: 'var(--color-lane-workshop)',
    label: 'WORKSHOP · Built At Stick',
    purpose: 'Proves technical capability.',
  },
  human: {
    color: 'var(--color-lane-human)',
    label: 'HUMAN / TRUST',
    purpose: 'Shows the real people behind Stick.',
  },
  apparel: {
    color: 'var(--color-lane-apparel)',
    label: 'APPAREL · Style That Belongs',
    purpose: 'Keeps clothing + style visible.',
  },
  campaign: {
    color: 'var(--color-lane-campaign)',
    label: 'CAMPAIGN',
    purpose: 'Supports seasonal / sales pushes.',
  },
  paid: {
    color: 'var(--color-lane-paid)',
    label: 'PAID',
    purpose: 'Active media support.',
  },
  search: {
    color: 'var(--color-lane-search)',
    label: 'SEARCH',
    purpose: 'Owned-content + website actions.',
  },
  commercial: {
    color: 'var(--color-lane-commercial)',
    label: 'COMMERCIAL',
    purpose: 'Direct-response CTA push.',
  },
  crm: {
    color: 'var(--color-lane-crm)',
    label: 'CRM',
    purpose: 'Lifecycle + repeat.',
  },
}

export const PIN_COLORS: Record<
  string,
  { bg: string; fg: string; bar: string; barBg: string; label: string }
> = {
  'A-PIN': {
    bg: 'rgba(240,160,48,0.18)',
    fg: '#f0a030',
    bar: '#f0a030',
    barBg: 'rgba(240,160,48,0.10)',
    label: 'A-PIN major commercial',
  },
  'B-PIN': {
    bg: 'rgba(20,184,166,0.16)',
    fg: '#14b8a6',
    bar: '#14b8a6',
    barBg: 'rgba(20,184,166,0.10)',
    label: 'B-PIN content week',
  },
  'C-PIN': {
    bg: 'rgba(148,163,184,0.10)',
    fg: '#94a3b8',
    bar: '#94a3b8',
    barBg: 'rgba(148,163,184,0.06)',
    label: 'C-PIN light hook',
  },
}

export const LANE_FILTER_ORDER = Object.keys(LANE_META)

/** Local calendar YYYY-MM-DD (fixes Classic UTC slice bug B3). */
export function formatLocalIso(d: Date): string {
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const da = String(d.getDate()).padStart(2, '0')
  return `${y}-${mo}-${da}`
}

export function localTodayIso(from: Date = new Date()): string {
  return formatLocalIso(from)
}

export function shiftMonthParam(monthParam: string, delta: number): string {
  const [y, m] = monthParam.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export type MonthGridCell = {
  iso: string
  dayNum: number
  inMonth: boolean
  isWeekend: boolean
  isToday: boolean
}

/** Build month grid cells with correct ISO for padding days (fixes Classic B2). */
export function buildMonthGridCells(
  year: number,
  month1: number,
  todayIso: string,
): MonthGridCell[] {
  const first = new Date(year, month1 - 1, 1)
  const firstDow = (first.getDay() + 6) % 7
  const lastDay = new Date(year, month1, 0).getDate()
  const raw: { date: Date; inMonth: boolean }[] = []

  for (let i = firstDow - 1; i >= 0; i--) {
    raw.push({ date: new Date(year, month1 - 1, 1 - (i + 1)), inMonth: false })
  }
  for (let d = 1; d <= lastDay; d++) {
    raw.push({ date: new Date(year, month1 - 1, d), inMonth: true })
  }
  while (raw.length % 7 !== 0) {
    const last = raw[raw.length - 1].date
    raw.push({
      date: new Date(last.getFullYear(), last.getMonth(), last.getDate() + 1),
      inMonth: false,
    })
  }

  return raw.map(({ date, inMonth }) => {
    const iso = formatLocalIso(date)
    const dowIdx = (date.getDay() + 6) % 7
    return {
      iso,
      dayNum: date.getDate(),
      inMonth,
      isWeekend: dowIdx >= 5,
      isToday: iso === todayIso,
    }
  })
}

export function filterMonthItemsByLane(
  items: PlanningMonthItem[] | undefined,
  laneFilter: string,
): PlanningMonthItem[] {
  const list = items || []
  if (!laneFilter) return list
  return list.filter((it) => it.lane === laneFilter)
}

export function truncateChipTitle(title: string, max = 18): string {
  if (title.length <= max) return title
  return `${title.slice(0, max)}…`
}

export function brandDisplayName(brand: string): string {
  if (brand === 'stick') return 'STICK'
  if (brand === 'swing-shack') return 'SWING SHACK'
  if (brand === 'bag-drop') return 'BAG DROP'
  return brand.toUpperCase()
}

export function deadlineDayLabel(todayIso: string, dueIso: string): string {
  const dueDate = new Date(`${dueIso}T00:00:00`)
  const today = new Date(`${todayIso}T00:00:00`)
  const days = Math.round((dueDate.getTime() - today.getTime()) / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  return `in ${days} days`
}

export function findFeaturedDate(
  days: Record<string, PlanningMonthItem[]> | undefined,
  monthPrefix: string,
): string | null {
  if (!days) return null
  const entries = Object.entries(days).filter(([d]) => d.startsWith(monthPrefix))
  if (entries.length === 0) return null
  const densest = entries.sort((a, b) => b[1].length - a[1].length)[0]
  if (densest && densest[1].length >= 4) return densest[0]
  return null
}

export function monthSummaryStats(
  days: Record<string, PlanningMonthItem[]> | undefined,
  monthPrefix: string,
): { totalItems: number; activeDays: number } {
  if (!days) return { totalItems: 0, activeDays: 0 }
  let totalItems = 0
  let activeDays = 0
  for (const [d, items] of Object.entries(days)) {
    if (!d.startsWith(monthPrefix)) continue
    activeDays += 1
    totalItems += items.length
  }
  return { totalItems, activeDays }
}

const planningEventCache = new Map<string, unknown>()

export function getCachedPlanningEvent(key: string): unknown | undefined {
  return planningEventCache.get(key)
}

export function setCachedPlanningEvent(key: string, data: unknown): void {
  planningEventCache.set(key, data)
}

export function planningEventCacheKey(brand: string, eventId: string): string {
  return `${brand}:${eventId}`
}
