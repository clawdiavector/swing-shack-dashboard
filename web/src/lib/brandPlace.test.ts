import { describe, expect, it } from 'vitest'
import { farAwayLabel } from './brandPlace'

// Audit 3 Nov 2026: the scout offered Stick (Paarl) a Johannesburg event as "local".
describe('farAwayLabel', () => {
  it('names the place and where the brand is', () => {
    expect(farAwayLabel({ far_from_brand: { place: 'Johannesburg', home: 'Paarl' } }, 'Stick')).toBe(
      'Far away: Johannesburg (Stick is in Paarl)',
    )
  })
  it('is empty when the suggestion is local or the brand is unknown', () => {
    expect(farAwayLabel({ far_from_brand: null }, 'Stick')).toBe('')
    expect(farAwayLabel(undefined, 'Stick')).toBe('')
    expect(farAwayLabel({ far_from_brand: { place: 'Durban', home: 'Johannesburg' } })).toBe(
      'Far away: Durban (the brand is in Johannesburg)',
    )
  })
})
