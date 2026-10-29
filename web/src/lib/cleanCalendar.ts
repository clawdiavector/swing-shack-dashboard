// The clean calendar: Scheduled, Needs your OK and Ideas, one at a time.
// Data and wording come from /api/clean-calendar (campaign-os/_lib/clean_calendar.py).

export type CleanView = 'scheduled' | 'approval' | 'ideas' | 'todo'
// 'edit' (a new caption) is offered only when an entry is editable, never as a button in `actions`.
export type CleanAction = 'approve' | 'comment' | 'reject' | 'edit'

export type CleanComment = {
  who: string
  text: string
  action: string
  at: string
}

export type CleanEntry = {
  key: string
  kind: 'post' | 'idea' | 'postiz' | 'gbp' | 'task'
  view: CleanView
  making: boolean
  missed?: boolean
  rejected?: boolean
  movable?: boolean
  editable?: boolean
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
  link?: string
  plan_id?: string
  actions: CleanAction[]
  comments: CleanComment[]
}

// The daily posting target (campaign-os/_lib/daily_target.py): placements per
// platform slot, how many are scheduled (done) and how many wait for a yes.
export type TargetSlot = {
  slot: string
  label: string
  target: number
  done: number
  waiting: number
}

// The day's lead category, first in `order`, and what to push for it.
export type DayLead = {
  order: { group: string; label: string; count: number }[]
  push: string[]
}

export type DayTarget = {
  target: number
  done: number
  waiting: number
  slots: TargetSlot[]
  lead?: DayLead
}

export type CleanMonth = {
  ok: boolean
  brand: string
  brand_name: string
  month: string
  month_label: string
  counts: Record<CleanView, number>
  entries: CleanEntry[]
  targets?: Record<string, DayTarget>
  error?: string
}

export const VIEWS: { id: CleanView; label: string; hint: string }[] = [
  {
    id: 'scheduled',
    label: 'Scheduled',
    hint: 'Approved and set to go out on these days. Nothing to do.',
  },
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
  {
    id: 'todo',
    label: 'To do',
    hint: 'Planning, shoots, edits, reviews and boosts from your campaign plans.',
  },
]

export function pickStartView(counts: Pick<Record<CleanView, number>, 'scheduled' | 'approval' | 'ideas'>): CleanView {
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
    const j = (await res.json().catch(() => ({}))) as T & {
      ok?: boolean
      error?: string
    }
    if (!res.ok && j.ok === undefined) return { ok: false, error: `Something went wrong (${res.status}).` } as T
    return j
  } catch (e: unknown) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : 'Network problem.',
    } as T
  }
}

const base = (brand: string) => `/api/clean-calendar/${encodeURIComponent(brand)}`

export const fetchCleanMonth = (brand: string, month: string) =>
  call<CleanMonth>('GET', `${base(brand)}?month=${encodeURIComponent(month)}`)

export const actOnEntry = (
  brand: string,
  body: {
    key: string
    kind: string
    action: CleanAction
    text?: string
    month: string
  },
) => call<{ ok: boolean; message?: string; error?: string }>('POST', `${base(brand)}/act`, body)

export const moveEntry = (brand: string, body: { key: string; kind: string; date: string; month: string }) =>
  call<{ ok: boolean; message?: string; error?: string }>('POST', `${base(brand)}/move`, body)

export const makeShareLink = (brand: string, who = 'Herman', planId?: string) =>
  call<{
    ok: boolean
    share_url?: string
    expires_at?: string
    error?: string
  }>('POST', `${base(brand)}/share`, {
    who,
    plan_id: planId,
  })

export type CampaignSummary = {
  plan_id: string
  title: string
  event_date: string
  when: string
  status: string
}

export type CampaignStep = {
  item_id: string
  date: string
  when: string
  phase: string
  kind: string
  title: string
  owner: string
  shots: string[]
  note: string
  budget: number | null
  status: string
  entry: CleanEntry | null
}

export type CampaignTimeline = {
  ok: boolean
  plan_id: string
  title: string
  brand_name: string
  dates: string
  phases: { phase: string; from: string; to: string; count: number }[]
  steps: CampaignStep[]
  error?: string
}

export const PHASE_COLOUR: Record<string, string> = {
  Planning: '#8b80d8',
  Shoot: '#e0a030',
  'Edit and review': '#4f8fd8',
  Posts: '#2f9e6e',
  Boost: '#d4537e',
  Other: '#888780',
}

export const fetchCampaigns = (brand: string) =>
  call<{ ok: boolean; campaigns?: CampaignSummary[]; error?: string }>('GET', `${base(brand)}/campaigns`)

export const fetchCampaign = (brand: string, planId: string) =>
  call<CampaignTimeline>('GET', `${base(brand)}/campaign/${encodeURIComponent(planId)}`)

export const campaignPdfUrl = (brand: string, planId: string) =>
  `${base(brand)}/campaign/${encodeURIComponent(planId)}/print`
