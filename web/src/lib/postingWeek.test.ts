import { describe, expect, it } from 'vitest'
import {
  emptyWeekBuckets,
  formatGoesOut,
  formatPostingDayHeader,
  linkForPostState,
  nextActionFromStages,
  postingChannelLabel,
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

describe('nextActionFromStages', () => {
  it('waiting on caption when only booked is done', () => {
    expect(nextActionFromStages({ booked: true, caption: false })).toBe('Waiting on caption')
  })

  it('waiting on image when caption is done', () => {
    expect(
      nextActionFromStages({
        booked: true,
        caption: true,
        image: false,
      }),
    ).toBe('Waiting on image')
  })

  it('ready to review when image is done', () => {
    expect(
      nextActionFromStages({
        booked: true,
        caption: true,
        image: true,
        in_review: false,
      }),
    ).toBe('Ready to review')
  })

  it('needs your look when in review is done', () => {
    expect(
      nextActionFromStages({
        booked: true,
        caption: true,
        image: true,
        in_review: true,
        approved: false,
      }),
    ).toBe('Needs your look')
  })

  it('approved when approved stage is done but not queued', () => {
    expect(
      nextActionFromStages({
        booked: true,
        caption: true,
        image: true,
        in_review: true,
        approved: true,
        queued: false,
      }),
    ).toBe('Approved')
  })

  it('posted when all pipeline stages are done', () => {
    expect(
      nextActionFromStages({
        booked: true,
        caption: true,
        image: true,
        in_review: true,
        approved: true,
        queued: true,
        released: true,
        posted: true,
      }),
    ).toBe('Posted')
  })
})

describe('formatGoesOut', () => {
  it('uses weekday hint from the API day object', () => {
    expect(formatGoesOut('2026-09-24', 'Thu')).toBe('Goes out Thu 24 Sep')
  })
})

describe('postingChannelLabel', () => {
  it('maps facebook to Facebook', () => {
    expect(postingChannelLabel('facebook')).toBe('Facebook')
  })
})

describe('linkForPostState', () => {
  const stages = { booked: true, caption: false, image: false, in_review: false, approved: false, queued: false, released: false, posted: false }

  it('sends candidates to inbox', () => {
    expect(
      linkForPostState({ state: 'candidate', calendar_id: 'c1', title: 'T', stages }),
    ).toBe('/inbox')
  })

  it('sends draft_ready to review piece or review root', () => {
    expect(
      linkForPostState({
        state: 'draft_ready',
        calendar_id: 'c1',
        title: 'T',
        stages,
        inbox_item_id: 'draft_asset:a:b',
      }),
    ).toBe('/review/draft_asset%3Aa%3Ab')
    expect(linkForPostState({ state: 'draft_ready', calendar_id: 'c1', title: 'T', stages })).toBe(
      '/review',
    )
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
    expect(POSTING_STAGE_ORDER.length).toBe(8)
  })
})
