import { describe, expect, it } from 'vitest'
import {
  PHOTO_QUERY,
  TODAY_PATH,
  backTarget,
  listFilterFromQuery,
  mondayOfIso,
  photoFilterFromQuery,
  routeOwnsBrandQuery,
  withQueryParam,
} from './backNav'
import { persistedQuerySearch } from './queryState'

describe('back paths', () => {
  it('returns from a post to the same calendar week and brand', () => {
    const week = mondayOfIso('2026-10-23')
    const calendar = withQueryParam(new URLSearchParams('brand=stick&date=2026-10-23'), 'week', week)
    expect(calendar.get('week')).toBe('2026-10-19')
    expect(calendar.get('brand')).toBe('stick')
    expect(calendar.get('date')).toBe('2026-10-23')
    expect(backTarget({ idx: 1 })).toBeNull()
  })

  it('returns from a draft to the same review filter', () => {
    const review = withQueryParam(new URLSearchParams('brand=stick'), 'filter', 'no-brief')
    expect(review.get('filter')).toBe('no-brief')
    expect(routeOwnsBrandQuery('/review/draft-1')).toBe(true)
    expect(listFilterFromQuery(review.get('filter'))).toBe('no-brief')
    expect(backTarget({ idx: 1 })).toBeNull()
  })

  it('returns from a photo to the same filter and brand', () => {
    const list = new URLSearchParams('brand=stick&filter=approved')
    const opened = withQueryParam(list, PHOTO_QUERY, 'putter.jpg')
    expect(opened.get('filter')).toBe('approved')
    expect(opened.get('brand')).toBe('stick')
    expect(opened.get(PHOTO_QUERY)).toBe('putter.jpg')
    expect(photoFilterFromQuery(list.get('filter'))).toBe('approved')
    expect(backTarget({ idx: 1 })).toBeNull()
    const closed = withQueryParam(opened, PHOTO_QUERY, null)
    expect(closed.get(PHOTO_QUERY)).toBeNull()
    expect(closed.get('filter')).toBe('approved')
  })

  it('opens Today when there is no history and keeps brand, week, and filter', () => {
    expect(backTarget({ idx: 0 })).toBe(TODAY_PATH)
    expect(persistedQuerySearch('?brand=stick&week=2026-10-19&filter=approved&file=putter.jpg')).toBe(
      '?brand=stick&week=2026-10-19&filter=approved',
    )
  })
})
