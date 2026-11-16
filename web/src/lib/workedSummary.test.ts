import { describe, expect, it } from 'vitest'
import { bestPostSentence, learnSentence, postFormat, postWeekday, timesAverage } from './workedSummary'

describe('postFormat', () => {
  it('names the format in plain words', () => {
    expect(postFormat('VIDEO')).toBe('Reel')
    expect(postFormat('CAROUSEL_ALBUM')).toBe('Carousel')
    expect(postFormat('IMAGE')).toBe('Photo')
    expect(postFormat(undefined)).toBe('Post')
  })
})

describe('postWeekday', () => {
  it('gives the weekday of the timestamp', () => {
    expect(postWeekday('2026-11-03T09:00:00+0000')).toBe('Tuesday')
    expect(postWeekday(undefined)).toBe('')
  })
})

describe('timesAverage', () => {
  it('compares a post to the average', () => {
    expect(timesAverage(4.2, 1.4)).toBe(3)
    expect(timesAverage(1.5, 1.4)).toBeNull()
    expect(timesAverage(4, 0)).toBeNull()
    expect(timesAverage(undefined, 1.4)).toBeNull()
  })
})

describe('bestPostSentence', () => {
  it('says what to do more of when the best post beats the average', () => {
    const s = bestPostSentence(
      [{ engagementRate: 4.2, media_type: 'VIDEO', timestamp: '2026-11-03T09:00:00+0000' }],
      1.4,
    )
    expect(s).toContain('4.2%')
    expect(s).toContain('3×')
    expect(s).toMatch(/reel/i)
    expect(s).toMatch(/more/i)
  })
  it('stays honest when nothing stands out', () => {
    expect(bestPostSentence([{ engagementRate: 1.5 }], 1.4)).toMatch(/nothing stands out/i)
  })
  it('says so when there are no posts', () => {
    expect(bestPostSentence([], undefined)).toBe('')
  })
})

describe('learnSentence', () => {
  it('replaces LATE and zero counts with a sentence', () => {
    const s = learnSentence({ verdict: 'LATE', winners: 0, recipes: 0, samples: 5 })
    expect(s).not.toMatch(/LATE/)
    expect(s).toContain('5')
    expect(s).toMatch(/10/)
  })
  it('reports winners when there are some', () => {
    expect(learnSentence({ winners: 3, recipes: 2, samples: 14 })).toMatch(/3 winning/)
  })
})
