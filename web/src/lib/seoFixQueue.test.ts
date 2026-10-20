import { describe, expect, it } from 'vitest'
import { fixLabel, groupFixes, type SeoFix, type SeoFixQueue } from './seoFixQueue'

function fix(over: Partial<SeoFix>): SeoFix {
  return {
    id: 'x',
    source: 'seo',
    type: 'missing_h1',
    page: 'Coaching',
    severity: 'medium',
    message: null,
    fix: null,
    publish_policy: 'asks_first',
    status: 'draft',
    first_seen: '2026-10-19T04:00:00Z',
    ...over,
  }
}

function queue(items: SeoFix[]): SeoFixQueue {
  return { brand: 'swing-shack', updated: '2026-10-19T04:00:00Z', counts: { open: 0, auto_eligible: 0, asks_first: 0 }, items }
}

describe('groupFixes', () => {
  it('returns empty groups when there is no queue yet', () => {
    expect(groupFixes(null)).toEqual({ auto: [], ask: [] })
  })

  it('shows open fixes only', () => {
    const g = groupFixes(
      queue([fix({ id: 'a' }), fix({ id: 'b', status: 'resolved' }), fix({ id: 'c', status: 'dismissed' }), fix({ id: 'd', status: 'done' })]),
    )
    expect(g.ask.map((i) => i.id)).toEqual(['a'])
  })

  it('splits by publish policy and treats anything unknown as asks-first', () => {
    const g = groupFixes(
      queue([
        fix({ id: 'auto', publish_policy: 'auto_with_undo', type: 'missing_meta_description' }),
        fix({ id: 'ask' }),
        fix({ id: 'odd', publish_policy: 'something_else' as SeoFix['publish_policy'] }),
      ]),
    )
    expect(g.auto.map((i) => i.id)).toEqual(['auto'])
    expect(g.ask.map((i) => i.id).sort()).toEqual(['ask', 'odd'])
  })

  it('puts the worst problems first, then orders by page', () => {
    const g = groupFixes(
      queue([
        fix({ id: 'low', severity: 'low' }),
        fix({ id: 'high-z', severity: 'high', page: 'Membership' }),
        fix({ id: 'high-a', severity: 'high', page: 'Coaching' }),
        fix({ id: 'none', severity: null }),
      ]),
    )
    expect(g.ask.map((i) => i.id)).toEqual(['high-a', 'high-z', 'low', 'none'])
  })
})

describe('fixLabel', () => {
  it('uses plain words for known types and a readable fallback otherwise', () => {
    expect(fixLabel('missing_meta_description')).toBe('No search description')
    expect(fixLabel('brand_new_check')).toBe('brand new check')
  })
})
