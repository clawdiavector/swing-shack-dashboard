const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

export function parseDate(raw?: string | null) {
  if (!raw) return null
  const trimmed = String(raw).trim()
  if (!trimmed) return null
  const ymd = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (ymd) {
    const d = new Date(Number(ymd[1]), Number(ymd[2]) - 1, Number(ymd[3]))
    return Number.isNaN(d.getTime()) ? null : d
  }
  if (/^\d{10,13}$/.test(trimmed)) {
    const n = Number(trimmed)
    const d = new Date(trimmed.length === 10 ? n * 1000 : n)
    return Number.isNaN(d.getTime()) ? null : d
  }
  const d = new Date(trimmed)
  if (!Number.isNaN(d.getTime())) return d
  return null
}

function clock(d: Date) {
  let hours = d.getHours()
  const minutes = String(d.getMinutes()).padStart(2, '0')
  const ampm = hours >= 12 ? 'PM' : 'AM'
  hours = hours % 12 || 12
  return `${hours}:${minutes} ${ampm}`
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** Tuesday 22 September at 4:45 PM — Today / Yesterday when it is. */
export function formatStamp(iso?: string | null, fallback?: string | null) {
  const d = parseDate(iso) || parseDate(fallback) || new Date()
  const now = new Date()
  const day = startOfDay(d)
  const today = startOfDay(now)
  const diffDays = Math.round((today - day) / 86400000)
  const time = clock(d)

  if (diffDays === 0) return `Today at ${time}`
  if (diffDays === 1) return `Yesterday at ${time}`
  if (diffDays === -1) return `Tomorrow at ${time}`

  const weekday = WEEKDAYS[d.getDay()]
  const month = MONTHS[d.getMonth()]
  const yearBit = d.getFullYear() === now.getFullYear() ? '' : ` ${d.getFullYear()}`
  return `${weekday} ${d.getDate()} ${month}${yearBit} at ${time}`
}

export function isoDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Deep-link date param: YYYY-MM-DD only; junk falls back to today. */
export function parseIsoDateParam(raw: string | null | undefined): Date {
  if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return new Date()
  const d = parseDate(raw)
  if (!d || isoDate(d) !== raw) return new Date()
  return d
}

export function dayInMonth(raw: string | null | undefined, year: number, month0: number) {
  const d = parseDate(raw)
  if (!d) return null
  if (d.getFullYear() !== year || d.getMonth() !== month0) return null
  return d.getDate()
}

export function stampLabel(kind?: string) {
  if (kind === 'created') return 'Landed'
  if (kind === 'scheduled') return 'Goes live'
  if (kind === 'as_of') return 'As of'
  return 'Updated'
}
