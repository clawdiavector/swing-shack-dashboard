import { describe, expect, it } from 'vitest'
import { closesItem, fieldLabel, lengthState, resultNote, type ApplyResult } from './seoFixer'
import { splitByButton, type SeoFix, type SeoFixQueue } from './seoFixQueue'
import type { MetaChange } from './seoMetaPublish'

const entry = (over: Partial<MetaChange>): MetaChange => ({
  id: 'a',
  page: 'Membership',
  link: null,
  before: '',
  after: 'x',
  at: '2026-10-21T08:00:00Z',
  status: 'applied',
  verified: true,
  ...over,
})

describe('lengthState', () => {
  it('says what is wrong and by how much', () => {
    expect(lengthState('Too short', 120, 160)).toMatchObject({ state: 'short', count: 9 })
    expect(lengthState('x'.repeat(161), 120, 160).state).toBe('long')
    expect(lengthState('x'.repeat(140), 120, 160).state).toBe('ok')
  })

  it('counts the way the server does: trimmed, whitespace collapsed', () => {
    expect(lengthState('  a   b  ', 1, 10).count).toBe(3)
  })
})

describe('resultNote', () => {
  it('never claims the site changed in practice mode', () => {
    const r: ApplyResult = { ok: true, mode: 'dry-run', entry: entry({ status: 'dry_run' }) }
    expect(resultNote(r).text).toMatch(/Nothing on the website was changed/)
  })

  it('says so when a live change could not be confirmed', () => {
    expect(resultNote({ ok: true, entry: entry({ verified: false }) }).text).toMatch(/could not be confirmed/)
  })

  it('confirms a live change and points at Undo', () => {
    expect(resultNote({ ok: true, entry: entry({}) }).text).toMatch(/confirmed.*Undo/)
  })

  it('passes the server reason through on failure', () => {
    expect(resultNote({ ok: false, error: 'It names another company.' })).toEqual({ ok: false, text: 'It names another company.' })
  })
})

describe('closesItem', () => {
  it('only a change that reached the website closes the item', () => {
    expect(closesItem({ ok: true, entry: entry({}) })).toBe(true)
    expect(closesItem({ ok: true, entry: entry({ status: 'dry_run' }) })).toBe(false)
    expect(closesItem({ ok: false })).toBe(false)
  })
})

describe('fieldLabel', () => {
  it('treats older entries without a field as search descriptions', () => {
    expect(fieldLabel(undefined)).toBe('Search description')
    expect(fieldLabel('title')).toBe('Page title')
  })
})

function fix(over: Partial<SeoFix>): SeoFix {
  return {
    id: 'x',
    source: 'seo',
    type: 'missing_h1',
    page: 'Membership',
    severity: 'medium',
    message: null,
    fix: null,
    publish_policy: 'asks_first',
    status: 'draft',
    first_seen: '2026-10-21T04:00:00Z',
    ...over,
  }
}

describe('splitByButton', () => {
  const q = (items: SeoFix[]): SeoFixQueue => ({
    brand: 'swing-shack',
    updated: '2026-10-21T04:00:00Z',
    counts: { open: 0, auto_eligible: 0, asks_first: 0 },
    items,
  })

  it('puts anything with a button in the click group whatever its policy', () => {
    const g = splitByButton(
      q([
        fix({ id: 'a', type: 'missing_meta_description', publish_policy: 'auto_with_undo', fix_button: { field: 'meta_description', label: 'Fix' } }),
        fix({ id: 'b', type: 'title_too_short', fix_button: { field: 'title', label: 'Improve' } }),
        fix({ id: 'c', type: 'missing_h1' }),
      ]),
    )
    expect(g.click.map((i) => i.id).sort()).toEqual(['a', 'b'])
    expect(g.rest.map((i) => i.id)).toEqual(['c'])
  })

  it('ignores items that are not open and handles no queue', () => {
    expect(splitByButton(null)).toEqual({ click: [], rest: [] })
    expect(splitByButton(q([fix({ status: 'resolved', fix_button: { field: 'title', label: 'Improve' } })])).click).toEqual([])
  })
})
