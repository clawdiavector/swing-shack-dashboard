import { brandRank } from './brands'
import { sumCounts } from './mergeCounts'
import type { PostingWeekDay, PostingWeekPost, PostingWeekPayload, ShelfPayload } from './postingWeek'

export type FanOutFailure = { brandId: string; error: string }

export type FanOutResult<T> = {
  rows: T[]
  failures: FanOutFailure[]
  partial: boolean
}

type OkPayload = { ok?: boolean; error?: string }

async function runPool<T>(
  brandIds: string[],
  concurrency: number,
  worker: (brandId: string) => Promise<T>,
): Promise<Array<{ brandId: string; status: 'fulfilled'; value: T } | { brandId: string; status: 'rejected'; reason: unknown }>> {
  const results: Array<
    { brandId: string; status: 'fulfilled'; value: T } | { brandId: string; status: 'rejected'; reason: unknown }
  > = []
  let cursor = 0
  async function runOne() {
    while (cursor < brandIds.length) {
      const i = cursor++
      const brandId = brandIds[i]!
      try {
        const value = await worker(brandId)
        results.push({ brandId, status: 'fulfilled', value })
      } catch (reason) {
        results.push({ brandId, status: 'rejected', reason })
      }
    }
  }
  const n = Math.min(concurrency, brandIds.length)
  await Promise.all(Array.from({ length: n }, () => runOne()))
  return results
}

function failureMessage(reason: unknown, payload?: OkPayload): string {
  if (payload?.ok === false) return payload.error || 'Request failed'
  if (reason instanceof Error) return reason.message
  return String(reason)
}

export async function fanOut<P extends OkPayload, T>(
  brandIds: string[],
  fetch: (brandId: string) => Promise<P>,
  extract: (payload: P, brandId: string) => T[],
  opts?: { concurrency?: number },
): Promise<FanOutResult<T>> {
  const concurrency = opts?.concurrency ?? 3
  const settled = await runPool(brandIds, concurrency, fetch)
  const failures: FanOutFailure[] = []
  const rows: T[] = []
  for (const entry of settled) {
    if (entry.status === 'rejected') {
      failures.push({ brandId: entry.brandId, error: failureMessage(entry.reason) })
      continue
    }
    const payload = entry.value
    if (payload.ok === false) {
      failures.push({ brandId: entry.brandId, error: failureMessage(undefined, payload) })
      continue
    }
    rows.push(...extract(payload, entry.brandId))
  }
  return {
    rows,
    failures,
    partial: failures.length > 0 && rows.length > 0,
  }
}

export function sortPostsByBrandThenTitle(
  posts: PostingWeekPost[],
  orderedBrandIds: string[],
): PostingWeekPost[] {
  return [...posts].sort((a, b) => {
    const ra = brandRank(a.brand_id || '', orderedBrandIds)
    const rb = brandRank(b.brand_id || '', orderedBrandIds)
    if (ra !== rb) return ra - rb
    const ta = a.title || ''
    const tb = b.title || ''
    const cmp = ta.localeCompare(tb)
    if (cmp !== 0) return cmp
    const ca = a.calendar_id || ''
    const cb = b.calendar_id || ''
    return ca.localeCompare(cb)
  })
}

function mergeHolidayLists(lists: Array<{ title?: string }[] | undefined>): { title?: string }[] {
  const seen = new Set<string>()
  const out: { title?: string }[] = []
  for (const list of lists) {
    for (const h of list || []) {
      const key = (h.title || '').trim().toLowerCase()
      if (!key || seen.has(key)) continue
      seen.add(key)
      out.push(h)
    }
  }
  return out
}

export function mergePostingWeekPayloads(
  parts: Array<{ brandId: string; payload: PostingWeekPayload }>,
  orderedBrandIds: string[],
): PostingWeekPayload {
  const okParts = parts.filter((p) => p.payload.ok !== false)
  if (okParts.length === 0) {
    return { ok: false, error: parts[0]?.payload.error || 'Failed to load week' }
  }
  const dayMap = new Map<string, PostingWeekDay>()
  for (const { brandId, payload } of okParts) {
    for (const day of payload.days_list || []) {
      const tagged = (day.posts || []).map((post) => ({
        ...post,
        brand_id: post.brand_id ?? brandId,
      }))
      const existing = dayMap.get(day.date)
      if (!existing) {
        dayMap.set(day.date, {
          ...day,
          posts: sortPostsByBrandThenTitle(tagged, orderedBrandIds),
          holidays: day.holidays,
        })
      } else {
        const mergedPosts = sortPostsByBrandThenTitle(
          [...existing.posts, ...tagged],
          orderedBrandIds,
        )
        dayMap.set(day.date, {
          ...existing,
          is_today: existing.is_today || day.is_today,
          is_past: existing.is_past || day.is_past,
          posts: mergedPosts,
          holidays: mergeHolidayLists([existing.holidays, day.holidays]),
        })
      }
    }
  }
  const days_list = [...dayMap.values()].sort((a, b) => a.date.localeCompare(b.date))
  const undatedTagged: PostingWeekPost[] = []
  let undated_total = 0
  for (const { brandId, payload } of okParts) {
    undated_total += payload.undated_total ?? payload.undated?.length ?? 0
    for (const post of payload.undated || []) {
      undatedTagged.push({ ...post, brand_id: post.brand_id ?? brandId })
    }
  }
  const undated = sortPostsByBrandThenTitle(undatedTagged, orderedBrandIds)
  const counts = sumCounts(okParts.map((p) => p.payload.counts))
  return {
    ok: true,
    days_list,
    undated,
    undated_total,
    counts,
  }
}

export function mergeShelfPayloads(
  parts: Array<{ brandId: string; payload: ShelfPayload }>,
  orderedBrandIds: string[],
): ShelfPayload {
  const okParts = parts.filter((p) => p.payload.ok !== false)
  if (okParts.length === 0) {
    return { ok: false, error: parts[0]?.payload.error || 'Failed to load shelf' }
  }
  const groupMap = new Map<string, PostingWeekPost[]>()
  const undatedTagged: PostingWeekPost[] = []
  for (const { brandId, payload } of okParts) {
    for (const group of payload.date_groups || []) {
      const tagged = (group.posts || []).map((post) => ({
        ...post,
        brand_id: post.brand_id ?? brandId,
      }))
      const prev = groupMap.get(group.date) || []
      groupMap.set(group.date, [...prev, ...tagged])
    }
    for (const post of payload.undated || []) {
      undatedTagged.push({ ...post, brand_id: post.brand_id ?? brandId })
    }
  }
  const date_groups = [...groupMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, posts]) => ({
      date,
      posts: sortPostsByBrandThenTitle(posts, orderedBrandIds),
    }))
  const counts = sumCounts(okParts.map((p) => p.payload.counts))
  return {
    ok: true,
    date_groups,
    undated: sortPostsByBrandThenTitle(undatedTagged, orderedBrandIds),
    counts,
  }
}

export async function fanOutPayloads<P extends OkPayload>(
  brandIds: string[],
  fetch: (brandId: string) => Promise<P>,
  opts?: { concurrency?: number },
): Promise<{ payloads: Array<{ brandId: string; payload: P }>; failures: FanOutFailure[]; partial: boolean }> {
  const concurrency = opts?.concurrency ?? 3
  const settled = await runPool(brandIds, concurrency, fetch)
  const failures: FanOutFailure[] = []
  const payloads: Array<{ brandId: string; payload: P }> = []
  for (const entry of settled) {
    if (entry.status === 'rejected') {
      failures.push({ brandId: entry.brandId, error: failureMessage(entry.reason) })
      continue
    }
    const payload = entry.value
    if (payload.ok === false) {
      failures.push({ brandId: entry.brandId, error: failureMessage(undefined, payload) })
      continue
    }
    payloads.push({ brandId: entry.brandId, payload })
  }
  return {
    payloads,
    failures,
    partial: failures.length > 0 && payloads.length > 0,
  }
}
