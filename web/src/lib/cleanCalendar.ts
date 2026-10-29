// The clean calendar: Scheduled, Needs your OK and Ideas, one at a time.
// Data and wording come from /api/clean-calendar (campaign-os/_lib/clean_calendar.py).

export type CleanView = 'scheduled' | 'approval' | 'ideas'
export type CleanAction = 'approve' | 'comment' | 'reject'

export type CleanComment = { who: string; text: string; action: string; at: string }

export type CleanEntry = {
  key: string
  kind: 'post' | 'idea'
  view: CleanView
  making: boolean
  state: string
  date: string
  when: string
  where: string
  brand_name: string
  title: string
  what: string
  why: string
  caption: string
  status: string
  next?: string
  has_image: boolean
  image: string | null
  actions: CleanAction[]
  comments: CleanComment[]
}

export type CleanMonth = {
  ok: boolean
  brand: string
  brand_name: string
  month: string
  month_label: string
  counts: Record<CleanView, number>
  entries: CleanEntry[]
  error?: string
}

export const VIEWS: { id: CleanView; label: string; hint: string }[] = [
  { id: 'scheduled', label: 'Scheduled', hint: 'Approved and set to go out on these days. Nothing to do.' },
  {
    id: 'approval',
    label: 'Needs your OK',
    hint: 'Ready posts waiting for a yes. Faded ones are still being made and come back here when ready.',
  },
  {
    id: 'ideas',
    label: 'Ideas',
    hint: 'Ideas only, nothing made yet. Approve one and the post gets made, then comes back under Needs your OK.',
  },
]

export function pickStartView(counts: Record<CleanView, number>): CleanView {
  if (counts.approval > 0) return 'approval'
  if (counts.scheduled > 0) return 'scheduled'
  if (counts.ideas > 0) return 'ideas'
  return 'scheduled'
}

export function shiftMonth(month: string, step: number): string {
  const [y, m] = month.split('-').map(Number)
  const idx = y * 12 + (m - 1) + step
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, '0')}`
}

export function thisMonth(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** Monday-first cells for a month; null pads the first and last week. */
export function monthCells(month: string): ({ iso: string; day: number } | null)[] {
  const [y, m] = month.split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const days = new Date(y, m, 0).getDate()
  const lead = (first.getDay() + 6) % 7
  const cells: ({ iso: string; day: number } | null)[] = Array(lead).fill(null)
  for (let d = 1; d <= days; d++) {
    cells.push({ iso: `${month}-${String(d).padStart(2, '0')}`, day: d })
  }
  while (cells.length % 7) cells.push(null)
  return cells
}

export function dayEntries(entries: CleanEntry[], iso: string, view: CleanView): CleanEntry[] {
  return entries.filter((e) => e.date === iso && e.view === view)
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  try {
    const res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    const j = (await res.json().catch(() => ({}))) as T & { ok?: boolean; error?: string }
    if (!res.ok && j.ok === undefined) return { ok: false, error: `Something went wrong (${res.status}).` } as T
    return j
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.' } as T
  }
}

const base = (brand: string) => `/api/clean-calendar/${encodeURIComponent(brand)}`

export const fetchCleanMonth = (brand: string, month: string) =>
  call<CleanMonth>('GET', `${base(brand)}?month=${encodeURIComponent(month)}`)

export const actOnEntry = (
  brand: string,
  body: { key: string; kind: string; action: CleanAction; text?: string; month: string },
) => call<{ ok: boolean; message?: string; error?: string }>('POST', `${base(brand)}/act`, body)

export const makeShareLink = (brand: string, who = 'Herman') =>
  call<{ ok: boolean; share_url?: string; expires_at?: string; error?: string }>('POST', `${base(brand)}/share`, {
    who,
  })
