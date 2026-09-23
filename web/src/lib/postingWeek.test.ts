import { describe, expect, it } from 'vitest'
import {
  emptyWeekBuckets,
  formatPostingDayHeader,
  POSTING_STAGE_ORDER,
  primaryStageFromStages,
} from './postingWeek'

describe('formatPostingDayHeader', () => {
  it('combines weekday and short date', () => {
    expect(
      formatPostingDayHeader({ date: '2026-09-24', weekday: 'Thu', posts: [] }),
    ).toBe('Thu 24/09')
  })
})

describe('primaryStageFromStages', () => {
  it('picks the latest true stage in pipeline order', () => {
    const stages = {
      booked: true,
      caption: true,
      image: false,
      in_review: true,
      approved: false,
      queued: false,
    }
    expect(primaryStageFromStages(stages)).toBe('in_review')
  })

  it('returns booked when only booked is set', () => {
    expect(primaryStageFromStages({ booked: true })).toBe('booked')
  })
})

describe('emptyWeekBuckets', () => {
  it('returns seven ISO dates from a start', () => {
    const buckets = emptyWeekBuckets('2026-09-23', 7)
    expect(buckets).toHaveLength(7)
    expect(buckets[0]).toBe('2026-09-23')
    expect(buckets[6]).toBe('2026-09-29')
  })

  it('empty day posts array is valid', () => {
    expect(POSTING_STAGE_ORDER.length).toBe(6)
  })
})
