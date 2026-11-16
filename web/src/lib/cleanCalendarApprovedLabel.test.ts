import { describe, expect, it } from 'vitest'
import { VIEWS } from './cleanCalendar'

// Audit 5 Nov 2026: the calendar box said "Scheduled 20" next to the "Scheduled 4" tile.
// The box holds every approved post this month, sent ones included; the tile holds the ones still waiting.
describe('calendar approved box', () => {
  const box = VIEWS.find((v) => v.id === 'scheduled')

  it('is called Approved, not Scheduled', () => {
    expect(box?.label).toBe('Approved')
    expect(VIEWS.map((v) => v.label)).not.toContain('Scheduled')
  })
  it('says it includes posts that already went out', () => {
    expect(box?.hint).toMatch(/already (went|gone) out/i)
  })
})
