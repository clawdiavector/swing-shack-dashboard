/** Header Back: history when the router has some, otherwise Today. */

export const TODAY_PATH = '/daily'

export const BRAND_QUERY = 'brand'
export const FILTER_QUERY = 'filter'
export const WEEK_QUERY = 'week'
export const PHOTO_QUERY = 'file'

const PHOTO_FILTERS = ['needs-check', 'approved', 'rejected', 'inbox', 'video'] as const

export type PhotoFilter = (typeof PHOTO_FILTERS)[number]

/** React Router stores the stack position on history.state.idx. 0 is a direct open. */
export function historyIndex(state: unknown): number {
  if (!state || typeof state !== 'object') return 0
  const idx = (state as { idx?: unknown }).idx
  return typeof idx === 'number' && Number.isFinite(idx) ? idx : 0
}

/**
 * Null means go back one history entry.
 * A path means there is nothing to go back to, so open Today.
 */
export function backTarget(state: unknown): string | null {
  return historyIndex(state) > 0 ? null : TODAY_PATH
}

/** Strip the /app basename so route checks match useLocation().pathname. */
export function appPathname(pathname: string): string {
  if (pathname === '/app') return '/'
  if (pathname.startsWith('/app/')) return pathname.slice(4) || '/'
  return pathname || '/'
}

/**
 * A review piece already uses ?brand= for that piece.
 * The desk brand query must not overwrite it.
 */
export function routeOwnsBrandQuery(pathname: string): boolean {
  const parts = appPathname(pathname).split('/').filter(Boolean)
  return parts[0] === 'review' && parts.length === 2 && parts[1] !== 'long-form'
}

/** Monday of the week that contains an ISO date. Null when the date is not real. */
export function mondayOfIso(iso: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(year, month - 1, day)
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null
  const delta = date.getDay() === 0 ? -6 : 1 - date.getDay()
  date.setDate(date.getDate() + delta)
  const mo = String(date.getMonth() + 1).padStart(2, '0')
  const da = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${mo}-${da}`
}

/** Copy `prev` and set or delete one key. Returns `prev` when nothing changed. */
export function withQueryParam(prev: URLSearchParams, key: string, value: string | null): URLSearchParams {
  const next = new URLSearchParams(prev)
  if (value) next.set(key, value)
  else next.delete(key)
  if (next.toString() === prev.toString()) return prev
  return next
}

/** Desk brand written into the query. `all` is the whole desk. */
export function deskBrandValue(scope: string, brandId: string | undefined): string {
  if (scope === 'all' || !brandId) return 'all'
  return brandId
}

export function listFilterFromQuery(raw: string | null): string {
  const value = (raw || '').trim()
  return value || 'all'
}

export function photoFilterFromQuery(raw: string | null): PhotoFilter {
  if (raw && (PHOTO_FILTERS as readonly string[]).includes(raw)) return raw as PhotoFilter
  return 'needs-check'
}
