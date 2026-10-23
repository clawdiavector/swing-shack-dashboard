import { describe, expect, it } from 'vitest'
import { persistedQuerySearch, withPersistedQuery } from './queryState'

describe('persisted query', () => {
  it('keeps brand, week, and filter and drops everything else', () => {
    expect(persistedQuerySearch('?brand=stick&week=2026-10-19&filter=retail&date=2026-10-23&file=a.jpg')).toBe(
      '?brand=stick&week=2026-10-19&filter=retail',
    )
  })

  it('carries those keys onto the next path without replacing a key that path already set', () => {
    expect(withPersistedQuery('/review/draft-1?brand=swing-shack', '?brand=stick&week=2026-10-19&filter=no-brief')).toBe(
      '/review/draft-1?brand=swing-shack&week=2026-10-19&filter=no-brief',
    )
  })

  it('returns the path alone when nothing is worth keeping', () => {
    expect(persistedQuerySearch('')).toBe('')
    expect(withPersistedQuery('/daily', '?file=a.jpg')).toBe('/daily')
  })
})
