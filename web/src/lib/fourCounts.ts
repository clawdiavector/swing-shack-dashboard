// The four counts every page shows, from /api/counts (campaign-os/_lib/four_counts.py).
import { useEffect, useState } from 'react'

export type FourCounts = {
  to_approve: number
  dates_to_decide: number
  scheduled: number
  sent_this_week: number
}

export type CountKey = keyof FourCounts

const TILES: Record<CountKey, { label: string; hint: string; to: string; tone: 'violet' | 'gold' | 'blue' | 'green' }> = {
  to_approve: { label: 'To approve', hint: 'Drafts waiting for your yes', to: '/review', tone: 'violet' },
  dates_to_decide: { label: 'Dates to decide', hint: 'Suggested dates in Inbox', to: '/inbox', tone: 'gold' },
  scheduled: { label: 'Scheduled', hint: 'Approved, waiting to go out', to: '/shelf', tone: 'blue' },
  sent_this_week: { label: 'Sent this week', hint: 'Sent from here since Monday', to: '/week', tone: 'green' },
}

const ORDER: CountKey[] = ['to_approve', 'dates_to_decide', 'scheduled', 'sent_this_week']

export function countTiles(c: FourCounts | null, keys: CountKey[] = ORDER) {
  return keys.map((k) => ({ key: k, ...TILES[k], value: c ? c[k] : ('—' as const) }))
}

const n = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`

/** Today's intro line. */
export function deskLine(c: FourCounts): string {
  return `${n(c.to_approve, 'draft', 'drafts')} to approve. ${n(c.dates_to_decide, 'date', 'dates')} to decide in Inbox. ${c.scheduled} scheduled to go out.`
}

/** Today's "What needs a call" row for publishing. */
export function shipLine(c: FourCounts): string {
  if (!c.scheduled && !c.sent_this_week) return 'Nothing scheduled to go out yet.'
  return `${c.scheduled} scheduled to go out. ${c.sent_this_week} sent this week.`
}

export async function fetchCounts(brand: string): Promise<FourCounts | null> {
  try {
    const res = await fetch(`/api/counts?brand=${encodeURIComponent(brand || 'all')}`, { credentials: 'same-origin' })
    if (!res.ok) return null
    const j = (await res.json()) as Partial<FourCounts> & { ok?: boolean }
    if (j.ok === false) return null
    return {
      to_approve: j.to_approve ?? 0,
      dates_to_decide: j.dates_to_decide ?? 0,
      scheduled: j.scheduled ?? 0,
      sent_this_week: j.sent_this_week ?? 0,
    }
  } catch {
    return null
  }
}

/** The counts for a brand ('' for all), refetched when it changes. */
export function useFourCounts(brand: string): FourCounts | null {
  const [counts, setCounts] = useState<FourCounts | null>(null)
  useEffect(() => {
    let cancelled = false
    setCounts(null)
    void fetchCounts(brand).then((c) => {
      if (!cancelled) setCounts(c)
    })
    return () => {
      cancelled = true
    }
  }, [brand])
  return counts
}
