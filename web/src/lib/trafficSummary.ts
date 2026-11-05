const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function shortDate(iso: string): string {
  const [, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]}`
}

/** "2026-10-28 to 2026-11-04" -> "28 Oct to 4 Nov". Empty when it is not in that shape. */
export function windowLabel(window?: string | null): string {
  const m = /^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/.exec(window || '')
  if (!m) return ''
  return `${shortDate(m[1])} to ${shortDate(m[2])}`
}

/** "/customer-portal/" -> "Customer portal". Long article slugs are cut at a word. */
export function pageLabel(path?: string | null): string {
  const slug = (path || '').replace(/^\/+|\/+$/g, '')
  if (!slug) return 'Home page'
  const words = slug.replace(/-/g, ' ')
  const text = words.charAt(0).toUpperCase() + words.slice(1)
  if (text.length <= 48) return text
  const cut = text.slice(0, 47)
  return `${cut.slice(0, cut.lastIndexOf(' '))}…`
}

export function trafficSentence(sessions?: number | null, window?: string | null): string {
  if (sessions == null) return ''
  const label = windowLabel(window)
  const visits = `${sessions.toLocaleString('en-ZA')} visits`
  if (!label) return `Your website had ${visits} in the latest week.`
  return `Your website had ${visits} between ${label.replace(' to ', ' and ')}.`
}

export type DaySpike = {
  date?: unknown
  ga4_sessions_on_day?: unknown
  ga4_sessions_baseline?: unknown
  lift_pct?: unknown
}

export function dayLabel(iso?: unknown): string {
  if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return ''
  const d = new Date(`${iso}T12:00:00Z`)
  const wd = d.toLocaleDateString('en-ZA', { weekday: 'short', timeZone: 'UTC' })
  return `${wd} ${shortDate(iso)}`
}

function times(lift: number): string {
  return lift >= 100 ? `${Math.round(lift / 100 + 1)}× as many` : `${Math.round(lift)}% more`
}

export function matchSentence(m: DaySpike): string {
  const day = dayLabel(m.date)
  const lift = Number(m.lift_pct)
  return `${day}: ${m.ga4_sessions_on_day} visits, against about ${m.ga4_sessions_baseline} on a usual day (${times(lift)}).`
}

export function spikeSentence(m: DaySpike): string {
  return `${dayLabel(m.date)}: ${m.ga4_sessions_on_day} visits, against about ${m.ga4_sessions_baseline} usually. We posted nothing that day or the day before.`
}
