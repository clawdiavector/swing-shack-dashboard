/** Kept on a direct-open Back to Today. Filter stays so the list you left is still named. */
const TODAY_QUERY_KEYS = ['brand', 'week', 'filter'] as const

/**
 * Copied when a rail link opens another section.
 * Filter is not copied: Review, Photos, and the calendar each mean something
 * different by that word, and history Back restores the page that set it.
 */
const CARRIED_QUERY_KEYS = ['brand', 'week'] as const

function keptSearch(search: string, keys: readonly string[]): string {
  const params = new URLSearchParams(search)
  const kept = new URLSearchParams()
  for (const key of keys) {
    const value = params.get(key)
    if (value && value.trim()) kept.set(key, value.trim())
  }
  const rendered = kept.toString()
  return rendered ? `?${rendered}` : ''
}

export function persistedQuerySearch(search: string): string {
  return keptSearch(search, TODAY_QUERY_KEYS)
}

export function withPersistedQuery(path: string, search: string): string {
  const [pathname, existingQuery = ''] = path.split('?')
  const merged = new URLSearchParams(existingQuery)
  const persisted = new URLSearchParams(keptSearch(search, CARRIED_QUERY_KEYS))
  for (const [key, value] of persisted.entries()) {
    if (!merged.get(key)) merged.set(key, value)
  }
  const rendered = merged.toString()
  return rendered ? `${pathname}?${rendered}` : pathname
}

