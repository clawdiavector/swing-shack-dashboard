// Client for /api/plan/v1: a dated, editable checklist built from a brief.
// Every call resolves to {ok, error?}; none throws, so the panel can show
// the server's own plain-language refusal ("the brief is not approved yet").

export type PlanItemKind =
  | 'research'
  | 'decide'
  | 'shoot'
  | 'edit'
  | 'review'
  | 'post'
  | 'story'
  | 'boost'

export type PlanItemStatus = 'proposed' | 'kept' | 'removed' | 'done'

export type PlanItem = {
  item_id: string
  kind: PlanItemKind
  title: string
  due: string
  days_before_event: number
  channel: string
  owner: string
  note: string
  needs_real_video: boolean
  late: boolean
  status: PlanItemStatus
  /** Set once the step is on the Main Calendar; '' otherwise. */
  calendar_id?: string
  source: 'template' | 'operator'
}

export type Plan = {
  plan_id: string
  brand_id: string
  brief_id: string
  brief_status?: string | null
  event_name: string
  event_date: string
  status: 'proposed' | 'approved' | 'superseded'
  /** The shape chosen for this kind of date, and why. */
  profile?: PlanProfile
  profile_label?: string
  profile_reason?: string
  approved_at?: string | null
  approved_by?: string | null
  /** When the steps were put on the calendar; null when they are not on it. */
  placed_at?: string | null
  items: PlanItem[]
}

export type PlanProfile = 'standard' | 'retail_push' | 'sport_event' | 'service_push' | 'season' | 'light'

/** The shapes a plan can take, with what each is for. */
export const PROFILE_OPTIONS: { id: PlanProfile; label: string; hint: string }[] = [
  { id: 'retail_push', label: 'Retail push', hint: 'Weeks of lead time, product shot early, a run of posts' },
  { id: 'sport_event', label: 'Sport event', hint: 'Build-up, game-day posts and a reaction after' },
  { id: 'service_push', label: 'Service push', hint: 'Fitting or coaching, aimed at bookings' },
  { id: 'season', label: 'Season', hint: 'A steady post every week for as long as it runs' },
  { id: 'light', label: 'Light touch', hint: 'One post and a story' },
  { id: 'standard', label: 'Standard', hint: 'The general shape' },
]

export type PlanResult = { ok: boolean; error?: string; plan?: Plan; existing?: boolean }

export const KIND_LABEL: Record<PlanItemKind, string> = {
  research: 'Check',
  decide: 'Decide',
  shoot: 'Shoot',
  edit: 'Edit',
  review: 'Approve',
  post: 'Post',
  story: 'Story',
  boost: 'Boost',
}

export const KIND_ORDER: PlanItemKind[] = [
  'research',
  'decide',
  'shoot',
  'edit',
  'review',
  'post',
  'story',
  'boost',
]

async function call(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<PlanResult> {
  try {
    const res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (res.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
      return { ok: false, error: 'Please sign in again.' }
    }
    const j = (await res.json().catch(() => ({}))) as PlanResult
    if (!res.ok || j.ok === false) {
      return { ok: false, error: j.error || `Something went wrong (${res.status}).` }
    }
    return j
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.' }
  }
}

const base = (brand: string) => `/api/plan/v1/${encodeURIComponent(brand)}`

/** The live plan for a brief, or null when none has been made. */
export async function findPlan(brand: string, briefId: string): Promise<PlanResult & { found: boolean }> {
  const r = (await call('GET', `${base(brand)}/list`)) as PlanResult & { plans?: Plan[] }
  if (!r.ok) return { ...r, found: false }
  const plan = (r.plans || []).find((p) => p.brief_id === briefId && p.status !== 'superseded')
  return { ok: true, plan, found: Boolean(plan) }
}

export const proposePlan = (brand: string, briefId: string, force = false, profile?: PlanProfile) =>
  call('POST', `${base(brand)}/propose`, { brief_id: briefId, force, ...(profile ? { profile } : {}) })

export const editPlanItem = (brand: string, planId: string, itemId: string, patch: Partial<PlanItem>) =>
  call('PATCH', `${base(brand)}/${encodeURIComponent(planId)}/item/${encodeURIComponent(itemId)}`, patch)

export const addPlanItem = (
  brand: string,
  planId: string,
  item: { title: string; due: string; kind: PlanItemKind; note?: string },
) => call('POST', `${base(brand)}/${encodeURIComponent(planId)}/item`, item)

export const approvePlan = (brand: string, planId: string) =>
  call('POST', `${base(brand)}/${encodeURIComponent(planId)}/approve`, {})

const NAME_KEY = 'cos_actor_name'

/** The calendar books a slot only for a named person. Ask once, remember it. */
export function actorName(ask: (q: string) => string | null = (q) => window.prompt(q)): string {
  try {
    const saved = window.localStorage.getItem(NAME_KEY)
    if (saved) return saved
  } catch {
    /* private window: ask every time */
  }
  const name = (ask('Your name, for the record (who is putting this on the calendar)?') || '').trim()
  if (name) {
    try {
      window.localStorage.setItem(NAME_KEY, name)
    } catch {
      /* ignore */
    }
  }
  return name
}

export const placePlan = (brand: string, planId: string, name: string) =>
  call('POST', `${base(brand)}/${encodeURIComponent(planId)}/place`, {}, { 'X-Actor-Display-Name': name })

export const unplacePlan = (brand: string, planId: string) =>
  call('POST', `${base(brand)}/${encodeURIComponent(planId)}/unplace`, {})

export const reopenPlan = (brand: string, planId: string) =>
  call('POST', `${base(brand)}/${encodeURIComponent(planId)}/reopen`, {})

function dayNumber(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return Math.round(Date.UTC(y, m - 1, d) / 86_400_000)
}

/** "in 12 days", "tomorrow", "today", "3 days ago". */
export function dueLabel(due: string, today: string): string {
  const n = dayNumber(due) - dayNumber(today)
  if (n === 0) return 'today'
  if (n === 1) return 'tomorrow'
  if (n === -1) return 'yesterday'
  return n > 0 ? `in ${n} days` : `${-n} days ago`
}

/** Items the operator still sees: removed ones hide behind an "undo" row. */
export function splitItems(items: PlanItem[]): { active: PlanItem[]; removed: PlanItem[] } {
  const sorted = [...items].sort(
    (a, b) => a.due.localeCompare(b.due) || KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind),
  )
  return {
    active: sorted.filter((i) => i.status !== 'removed'),
    removed: sorted.filter((i) => i.status === 'removed'),
  }
}

/** Why Approve is disabled, in words, or '' when it can go ahead. */
export function approveBlocker(plan: Plan): string {
  if (plan.brief_status !== 'approved') {
    return 'The brief is not approved yet. Approve the brief first, then this plan.'
  }
  const { active } = splitItems(plan.items)
  if (!active.length) return 'Every step is removed.'
  const hasBoost = active.some((i) => i.kind === 'boost')
  const hasVideo = active.some((i) => i.kind === 'shoot' && i.needs_real_video)
  if (hasBoost && !hasVideo) {
    return 'A boost needs real video with a person on camera. Add a video shoot or remove the boost.'
  }
  return ''
}

export function todayIso(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`
}

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "5 Dec 2026" from an ISO date. */
export function formatDay(iso?: string | null): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return iso
  return `${d} ${MONTH_ABBR[m - 1]} ${y}`
}

export type FromEventResult = PlanResult & {
  brief_id?: string
  brief_status?: string
  brief_existed?: boolean
}

/** One step from a calendar date to a draft plan: reuse the date's brief or
 *  write one, then propose the plan. */
export async function planFromEvent(brand: string, eventKey: string, force = false): Promise<FromEventResult> {
  const r = (await call('POST', `${base(brand)}/from-event`, { event_key: eventKey, force })) as FromEventResult
  return r
}
