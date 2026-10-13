import { describe, expect, it } from 'vitest'
import { cardPosition } from './MonthSuggestions'

const phone = { w: 375, h: 812 }

describe('cardPosition', () => {
  it('sits under the chip when there is room', () => {
    expect(cardPosition({ left: 20, top: 100, bottom: 118 }, phone)).toEqual({ left: 20, top: 122 })
  })
  it('is pulled back inside the right edge', () => {
    const p = cardPosition({ left: 300, top: 100, bottom: 118 }, phone)
    expect(p.left + 256).toBeLessThanOrEqual(375 - 8)
  })
  it('never starts off the left edge', () => {
    expect(cardPosition({ left: -40, top: 100, bottom: 118 }, phone).left).toBe(8)
  })
  it('flips above the chip near the bottom of the screen', () => {
    const p = cardPosition({ left: 20, top: 760, bottom: 778 }, phone)
    expect(p.top).toBeLessThan(760)
  })
})
