import { describe, expect, it } from 'vitest'
import { approveBlocker, dueLabel, splitItems, type Plan, type PlanItem } from './plan'

const item = (over: Partial<PlanItem>): PlanItem => ({
  item_id: 'it-1',
  kind: 'post',
  title: 'A post',
  due: '2026-12-01',
  days_before_event: 4,
  channel: '',
  owner: 'marketing',
  note: '',
  needs_real_video: false,
  late: false,
  status: 'proposed',
  source: 'template',
  ...over,
})

const plan = (items: PlanItem[], brief_status = 'approved'): Plan => ({
  plan_id: 'pln-1',
  brand_id: 'stick',
  brief_id: 'brf-1',
  brief_status,
  event_name: 'Black Friday',
  event_date: '2026-12-05',
  status: 'proposed',
  items,
})

describe('dueLabel', () => {
  it('speaks in days', () => {
    expect(dueLabel('2026-10-13', '2026-10-13')).toBe('today')
    expect(dueLabel('2026-10-14', '2026-10-13')).toBe('tomorrow')
    expect(dueLabel('2026-10-12', '2026-10-13')).toBe('yesterday')
    expect(dueLabel('2026-10-25', '2026-10-13')).toBe('in 12 days')
    expect(dueLabel('2026-10-10', '2026-10-13')).toBe('3 days ago')
  })
  it('counts across month and year ends', () => {
    expect(dueLabel('2027-01-02', '2026-12-30')).toBe('in 3 days')
  })
})

describe('splitItems', () => {
  it('sorts by date then step order and hides removed ones', () => {
    const r = splitItems([
      item({ item_id: 'a', due: '2026-12-02', kind: 'post' }),
      item({ item_id: 'b', due: '2026-12-01', kind: 'story' }),
      item({ item_id: 'c', due: '2026-12-01', kind: 'shoot' }),
      item({ item_id: 'd', due: '2026-11-30', status: 'removed' }),
    ])
    expect(r.active.map((i) => i.item_id)).toEqual(['c', 'b', 'a'])
    expect(r.removed.map((i) => i.item_id)).toEqual(['d'])
  })
})

describe('approveBlocker', () => {
  it('blocks until the brief is approved', () => {
    expect(approveBlocker(plan([item({})], 'draft'))).toMatch(/brief is not approved/)
  })
  it('blocks a boost with no real video shoot', () => {
    expect(approveBlocker(plan([item({ kind: 'boost' })]))).toMatch(/real video/)
  })
  it('lets a boost through with a video shoot', () => {
    const items = [item({ kind: 'boost' }), item({ item_id: 'v', kind: 'shoot', needs_real_video: true })]
    expect(approveBlocker(plan(items))).toBe('')
  })
  it('ignores a removed video shoot', () => {
    const items = [
      item({ kind: 'boost' }),
      item({ item_id: 'v', kind: 'shoot', needs_real_video: true, status: 'removed' }),
    ]
    expect(approveBlocker(plan(items))).toMatch(/real video/)
  })
  it('blocks an empty plan', () => {
    expect(approveBlocker(plan([item({ status: 'removed' })]))).toMatch(/removed/)
  })
})
