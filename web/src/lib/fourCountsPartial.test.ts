import { describe, expect, it } from 'vitest'
import { countTiles } from './fourCounts'

// Today already has the inbox numbers; it should not wait on the slow ones to show them.
describe('countTiles with some numbers known', () => {
  it('shows the known numbers and a dash for the rest', () => {
    const tiles = countTiles({ to_approve: 14, dates_to_decide: 59 })
    expect(tiles.map((t) => t.value)).toEqual([14, 59, '—', '—'])
  })
})
