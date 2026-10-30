import { describe, expect, it } from 'vitest'
import { dayEntries, monthCells, pickStartView, shiftMonth, type CleanEntry } from './cleanCalendar'

const entry = (over: Partial<CleanEntry>): CleanEntry => ({
  key: 'k',
  kind: 'post',
  view: 'scheduled',
  making: false,
  state: 'scheduled',
  date: '2026-11-02',
  when: 'Mon 2 Nov',
  where: 'Instagram',
  brand_name: 'Stick',
  title: 'A post',
  what: 'A feed post',
  why: '',
  caption: '',
  status: '',
  has_image: false,
  image: null,
  actions: ['comment'],
  comments: [],
  ...over,
})

describe('clean calendar grid', () => {
  it('lays a month out Monday first, padded to whole weeks', () => {
    const cells = monthCells('2026-11')
    expect(cells.length % 7).toBe(0)
    // 1 Nov 2026 is a Sunday, so six blanks lead.
    expect(cells.slice(0, 7).map((c) => c?.iso ?? null)).toEqual([null, null, null, null, null, null, '2026-11-01'])
    expect(cells.filter(Boolean)).toHaveLength(30)
  })

  it('moves across the year end', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(shiftMonth('2027-01', -1)).toBe('2026-12')
  })

  it('shows one view at a time, with posts being made under Needs your OK', () => {
    const all = [
      entry({ key: 'a', view: 'scheduled' }),
      entry({ key: 'b', view: 'approval', state: 'draft_ready' }),
      entry({ key: 'c', view: 'approval', making: true, state: 'drafting' }),
      entry({ key: 'd', view: 'ideas', kind: 'idea' }),
    ]
    expect(dayEntries(all, '2026-11-02', 'approval').map((e) => e.key)).toEqual(['b', 'c'])
    expect(dayEntries(all, '2026-11-02', 'ideas').map((e) => e.key)).toEqual(['d'])
    expect(dayEntries(all, '2026-11-03', 'scheduled')).toEqual([])
  })

  it('opens on what needs a yes when there is something, else on scheduled', () => {
    expect(pickStartView({ scheduled: 3, approval: 2, ideas: 5 })).toBe('approval')
    expect(pickStartView({ scheduled: 3, approval: 0, ideas: 5 })).toBe('scheduled')
    expect(pickStartView({ scheduled: 0, approval: 0, ideas: 5 })).toBe('ideas')
  })
})
