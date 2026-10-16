import { describe, expect, it } from 'vitest'
import { approveBlocker, boostBudget, draftState, dueLabel, formatRand, splitItems, type Plan, type PlanItem } from './plan'

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
  it('lets a draft brief through as long as one exists', () => {
    expect(approveBlocker(plan([item({})], 'draft'))).toBe('')
  })
  it('blocks when there is no brief', () => {
    expect(approveBlocker({ ...plan([item({})]), brief_id: '' })).toMatch(/no brief/)
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

describe('boost budget', () => {
  it('formats rand with gaps between thousands', () => {
    expect(formatRand(0)).toBe('R0')
    expect(formatRand(250)).toBe('R250')
    expect(formatRand(1500)).toBe('R1 500')
    expect(formatRand(1234567)).toBe('R1 234 567')
    expect(formatRand(250.5)).toBe('R250.5')
  })
  it('adds up the live boosts and counts those with no budget', () => {
    const items = [
      item({ item_id: 'a', kind: 'boost', budget: 1000 }),
      item({ item_id: 'b', kind: 'boost' }),
      item({ item_id: 'c', kind: 'boost', budget: 500, status: 'removed' }),
      item({ item_id: 'd', kind: 'post', budget: 99 }),
    ]
    expect(boostBudget(items)).toEqual({ total: 1000, boosts: 2, missing: 1 })
    expect(boostBudget([item({ kind: 'post' })])).toEqual({ total: 0, boosts: 0, missing: 0 })
  })
})

describe('draftState', () => {
  const post = (over: Partial<PlanItem> = {}) => item({ kind: 'post', calendar_id: 'cal-1', ...over })
  it('only a live post step has a draft to make', () => {
    expect(draftState(item({ kind: 'story' }), true).kind).toBe('none')
    expect(draftState(post({ status: 'removed' }), true).kind).toBe('none')
    expect(draftState(post({ status: 'done' }), true).kind).toBe('none')
  })
  it('says what is missing before it can be made, in the order the person does it', () => {
    expect(draftState(post(), false)).toEqual({ kind: 'wait', text: 'Approve the plan, and put it on the calendar, to make the draft.' })
    expect(draftState(post({ calendar_id: '' }), true)).toEqual({ kind: 'wait', text: 'Put the plan on the calendar to make the draft.' })
    expect(draftState(post(), true)).toEqual({ kind: 'ready' })
  })
  it('after it is asked for, says so and where it will appear', () => {
    const s = draftState(post({ draft: { requested_at: '2026-10-15T07:00:00+00:00', by: 'C', moment: 'm', queued: ['draft_caption'] } }), true)
    expect(s.kind).toBe('asked')
    expect(s.kind === 'asked' && s.text).toBe('Draft asked for on 15 Oct 2026. It appears in Approve drafts once the caption is written.')
  })
})
