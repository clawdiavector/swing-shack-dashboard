import { describe, expect, it } from 'vitest'
import {
  TODAY_PATH,
  backTarget,
  deskBrandValue,
  historyIndex,
  listFilterFromQuery,
  mondayOfIso,
  photoFilterFromQuery,
  routeOwnsBrandQuery,
  withQueryParam,
} from './backNav'

describe('backTarget', () => {
  it('goes to Today when the page was opened directly', () => {
    expect(historyIndex(null)).toBe(0)
    expect(historyIndex({})).toBe(0)
    expect(historyIndex({ idx: 0 })).toBe(0)
    expect(backTarget(null)).toBe(TODAY_PATH)
    expect(backTarget({ idx: 0 })).toBe(TODAY_PATH)
  })

  it('uses router history when there is a previous entry', () => {
    expect(historyIndex({ idx: 2 })).toBe(2)
    expect(backTarget({ idx: 1 })).toBeNull()
    expect(backTarget({ idx: 4 })).toBeNull()
  })
})

describe('routeOwnsBrandQuery', () => {
  it('leaves the piece brand on a review draft URL', () => {
    expect(routeOwnsBrandQuery('/review/draft-1')).toBe(true)
    expect(routeOwnsBrandQuery('/app/review/draft-1')).toBe(true)
  })

  it('lets the desk own brand on list pages', () => {
    expect(routeOwnsBrandQuery('/review')).toBe(false)
    expect(routeOwnsBrandQuery('/review/long-form')).toBe(false)
    expect(routeOwnsBrandQuery('/calendar')).toBe(false)
    expect(routeOwnsBrandQuery('/photos')).toBe(false)
    expect(routeOwnsBrandQuery('/week')).toBe(false)
  })
})

describe('week, filter, and brand query', () => {
  it('records the Monday of the calendar week', () => {
    expect(mondayOfIso('2026-10-23')).toBe('2026-10-19')
    expect(mondayOfIso('2026-10-19')).toBe('2026-10-19')
    expect(mondayOfIso('2026-10-25')).toBe('2026-10-19')
    expect(mondayOfIso('not-a-date')).toBeNull()
  })

  it('keeps an empty filter as All and a photo tab as itself', () => {
    expect(listFilterFromQuery(null)).toBe('all')
    expect(listFilterFromQuery('  ')).toBe('all')
    expect(listFilterFromQuery('no-brief')).toBe('no-brief')
    expect(photoFilterFromQuery(null)).toBe('needs-check')
    expect(photoFilterFromQuery('approved')).toBe('approved')
    expect(photoFilterFromQuery('nope')).toBe('needs-check')
  })

  it('writes brand, filter, and week without dropping the other keys', () => {
    const start = new URLSearchParams('date=2026-10-23')
    const withWeek = withQueryParam(start, 'week', '2026-10-19')
    const withBrand = withQueryParam(withWeek, 'brand', 'stick')
    const withFilter = withQueryParam(withBrand, 'filter', 'retail')
    expect(withFilter.get('date')).toBe('2026-10-23')
    expect(withFilter.get('week')).toBe('2026-10-19')
    expect(withFilter.get('brand')).toBe('stick')
    expect(withFilter.get('filter')).toBe('retail')
    expect(deskBrandValue('all', 'stick')).toBe('all')
    expect(deskBrandValue('stick', 'stick')).toBe('stick')
    const cleared = withQueryParam(withFilter, 'filter', null)
    expect(cleared.get('filter')).toBeNull()
    expect(cleared.get('brand')).toBe('stick')
    expect(withQueryParam(cleared, 'brand', 'stick')).toBe(cleared)
  })
})
