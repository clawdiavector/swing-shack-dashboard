import { describe, expect, it } from 'vitest'
import { applyNav, pageLabel, previousPath } from './navHistory'

describe('applyNav', () => {
  it('pushes a new page onto the trail', () => {
    expect(applyNav(['/daily'], '/week?tab=day&date=2026-10-02', 'PUSH')).toEqual([
      '/daily',
      '/week?tab=day&date=2026-10-02',
    ])
  })

  it('ignores a repeat of the current page', () => {
    expect(applyNav(['/week'], '/week', 'PUSH')).toEqual(['/week'])
  })

  it('replaces the current entry so a redirect does not become a back stop', () => {
    expect(applyNav(['/daily', '/review?view=week'], '/week', 'REPLACE')).toEqual(['/daily', '/week'])
  })

  it('pops back to the real previous page', () => {
    const stack = ['/daily', '/week?tab=day', '/review/piece-1']
    expect(applyNav(stack, '/week?tab=day', 'POP')).toEqual(['/daily', '/week?tab=day'])
    expect(previousPath(stack, '/review/piece-1')).toBe('/week?tab=day')
  })

  it('does not treat Review as the previous page when the user came from the week', () => {
    const stack = applyNav(['/week?tab=day&date=2026-10-02'], '/review/abc', 'PUSH')
    expect(previousPath(stack, '/review/abc')).toBe('/week?tab=day&date=2026-10-02')
    expect(previousPath(stack, '/review/abc')).not.toBe('/review')
  })
})

describe('pageLabel', () => {
  it('names the week desk, not Review, for a day url', () => {
    expect(pageLabel('/week?tab=day&date=2026-10-02')).toBe('This week')
  })
})
