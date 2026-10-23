const PERSISTED_QUERY_KEYS = ['brand', 'week', 'filter'] as const

type PersistedQueryKey = (typeof PERSISTED_QUERY_KEYS)[number]

export function persistedQuerySearch(search: string): string {
  const params = new URLSearchParams(search)
  const kept = new URLSearchParams()
  for (const key of PERSISTED_QUERY_KEYS) {
    const value = params.get(key)
    if (value && value.trim()) kept.set(key, value.trim())
  }
  const rendered = kept.toString()
  return rendered ? `?${rendered}` : ''
}

export function withPersistedQuery(path: string, search: string): string {
  const [pathname, existingQuery = ''] = path.split('?')
  const merged = new URLSearchParams(existingQuery)
  const persisted = new URLSearchParams(persistedQuerySearch(search))
  for (const [key, value] of persisted.entries()) {
    if (!merged.get(key)) merged.set(key, value)
  }
  const rendered = merged.toString()
  return rendered ? `${pathname}?${rendered}` : pathname
}

export function syncPersistedQueryValue(
  params: URLSearchParams,
  key: PersistedQueryKey,
  value: string,
): URLSearchParams {
  const next = new URLSearchParams(params)
  const trimmed = value.trim()
  if (trimmed) next.set(key, trimmed)
  else next.delete(key)
  return next
}

