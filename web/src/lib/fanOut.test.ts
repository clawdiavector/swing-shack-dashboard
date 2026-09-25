import { describe, expect, it } from 'vitest'
import {
  fanOut,
  fanOutPayloads,
  mergePostingWeekPayloads,
  sortPostsByBrandThenTitle,
} from './fanOut'
import type { PostingWeekPayload } from './postingWeek'
import { sumCounts } from './mergeCounts'

const ORDER = ['swing-shack', 'stick', 'bag-drop']

describe('fanOut', () => {
  it('merges rows and records partial failure', async () => {
    const result = await fanOut(
      ['swing-shack', 'stick', 'bag-drop'],
      async (brandId) => {
        if (brandId === 'stick') throw new Error('network')
        return { ok: true as const, items: [{ id: `${brandId}-1`, brand_id: brandId }] }
      },
      (payload, brandId) =>
        (payload.items || []).map((row) => ({ ...row, brand_id: row.brand_id ?? brandId })),
      { concurrency: 3 },
    )
    expect(result.rows).toHaveLength(2)
    expect(result.failures).toHaveLength(1)
    expect(result.failures[0]?.brandId).toBe('stick')
    expect(result.partial).toBe(true)
  })

  it('treats ok:false as failure', async () => {
    const { failures, payloads } = await fanOutPayloads(['swing-shack'], async () => ({
      ok: false,
      error: 'bad brand',
    }))
    expect(payloads).toHaveLength(0)
    expect(failures[0]?.error).toBe('bad brand')
  })
})

describe('mergePostingWeekPayloads', () => {
  it('joins days and sorts by brand order then title', () => {
    const a: PostingWeekPayload = {
      ok: true,
      days_list: [
        {
          date: '2026-09-25',
          weekday: 'Thu',
          posts: [{ calendar_id: 'c2', title: 'Zulu', stages: {} }],
        },
      ],
    }
    const b: PostingWeekPayload = {
      ok: true,
      days_list: [
        {
          date: '2026-09-25',
          weekday: 'Thu',
          posts: [{ calendar_id: 'c1', title: 'Alpha', stages: {} }],
        },
      ],
    }
    const merged = mergePostingWeekPayloads(
      [
        { brandId: 'stick', payload: a },
        { brandId: 'swing-shack', payload: b },
      ],
      ORDER,
    )
    expect(merged.days_list?.[0]?.posts.map((p) => p.title)).toEqual(['Alpha', 'Zulu'])
    expect(merged.days_list?.[0]?.posts[0]?.brand_id).toBe('swing-shack')
  })
})

describe('sortPostsByBrandThenTitle', () => {
  it('orders by brand rank then title', () => {
    const sorted = sortPostsByBrandThenTitle(
      [
        { calendar_id: '1', title: 'B', brand_id: 'stick', stages: {} },
        { calendar_id: '2', title: 'A', brand_id: 'swing-shack', stages: {} },
      ],
      ORDER,
    )
    expect(sorted.map((p) => p.brand_id)).toEqual(['swing-shack', 'stick'])
  })
})

describe('sumCounts', () => {
  it('sums numeric count fields', () => {
    const total = sumCounts([
      { pending: 2, stale: 1 },
      { pending: 3, stale: 0 },
    ])
    expect(total.pending).toBe(5)
    expect(total.stale).toBe(1)
  })
})
