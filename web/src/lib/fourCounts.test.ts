import { describe, expect, it } from 'vitest'
import { countTiles, deskLine, shipLine, type FourCounts } from './fourCounts'

const stick: FourCounts = { to_approve: 14, dates_to_decide: 59, scheduled: 4, sent_this_week: 4 }

describe('countTiles', () => {
  it('is the same four tiles, in order, linking to the list each counts', () => {
    const tiles = countTiles(stick)
    expect(tiles.map((t) => t.label)).toEqual(['To approve', 'Dates to decide', 'Scheduled', 'Sent this week'])
    expect(tiles.map((t) => t.to)).toEqual(['/review', '/inbox', '/shelf', '/week'])
    expect(tiles.map((t) => t.value)).toEqual([14, 59, 4, 4])
  })
  it('shows a dash while loading or when the counts failed', () => {
    expect(countTiles(null).map((t) => t.value)).toEqual(['—', '—', '—', '—'])
  })
  it('can show just the tiles a page needs', () => {
    expect(countTiles(stick, ['scheduled', 'sent_this_week']).map((t) => t.label)).toEqual(['Scheduled', 'Sent this week'])
  })
})

describe('deskLine', () => {
  it('uses the same numbers as the tiles', () => {
    expect(deskLine(stick)).toBe('14 drafts to approve. 59 dates to decide in Inbox. 4 scheduled to go out.')
    expect(deskLine({ to_approve: 1, dates_to_decide: 1, scheduled: 1, sent_this_week: 0 })).toBe(
      '1 draft to approve. 1 date to decide in Inbox. 1 scheduled to go out.',
    )
  })
})

describe('shipLine', () => {
  it('says what is scheduled, never "approved, not yet in the queue"', () => {
    expect(shipLine(stick)).toBe('4 scheduled to go out. 4 sent this week.')
    expect(shipLine({ ...stick, scheduled: 0, sent_this_week: 0 })).toBe('Nothing scheduled to go out yet.')
  })
})
