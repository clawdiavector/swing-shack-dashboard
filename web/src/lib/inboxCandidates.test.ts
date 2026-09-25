import { describe, expect, it } from 'vitest'
import type { InboxItem } from './api'
import { filterInboxCandidates, lodgeDisabled } from './inboxCandidates'

const base: InboxItem = {
  id: 'calendar_candidate:swing-shack:cal-1',
  type: 'calendar_candidate',
  meta: { flags: [], event_date: '2026-10-01', source_type: 'scout' },
}

describe('lodgeDisabled', () => {
  it('is true when no_date flag is set', () => {
    expect(lodgeDisabled(['no_date', 'holiday'])).toBe(true)
  })

  it('is false when a go-live date exists', () => {
    expect(lodgeDisabled(['holiday'])).toBe(false)
  })
})

describe('filterInboxCandidates', () => {
  it('filters by source and has-date', () => {
    const items: InboxItem[] = [
      base,
      {
        id: 'calendar_candidate:swing-shack:cal-2',
        type: 'calendar_candidate',
        meta: { flags: ['no_date'], created_by: 'holiday_inject' },
      },
      { id: 'draft_asset:x:y', type: 'draft_asset' },
    ]
    const dated = filterInboxCandidates(items, 'all', 'has-date')
    expect(dated).toHaveLength(1)
    expect(dated[0].id).toBe(base.id)
    const holidays = filterInboxCandidates(items, 'holiday', 'all')
    expect(holidays).toHaveLength(1)
    expect(holidays[0].id).toContain('cal-2')
  })
})
