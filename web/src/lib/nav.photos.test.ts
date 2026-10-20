import { describe, expect, it } from 'vitest'
import { RAIL, sectionFor, sectionPageFor } from './nav'

describe('Photos page', () => {
  it('lives in Today, as a tab after Stories', () => {
    expect(sectionFor('/photos')?.label).toBe('Today')
    const today = RAIL[0]
    expect(sectionPageFor(today, '/photos')).toBe('/photos')
    expect(today.pages.map((p) => p.label).at(-1)).toBe('Photos')
  })
})
