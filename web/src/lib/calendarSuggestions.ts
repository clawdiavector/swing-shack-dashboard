// Faded suggestions on the month calendar: dates waiting for a yes or a no.
// Calls resolve to {ok, error?}; none throws, so the card can show the
// server's own words.

export type SuggestionSource = 'yours' | 'scout' | 'date'

export type Suggestion = {
  key: string
  source: SuggestionSource
  title: string
  date: string
  end: string
  tier: string | null
  category: string
  why: string
  calendar_id: string | null
  /** Pillars the entry already carries; a brief needs at least one. */
  pillars?: string[]
  /** What kind of date it is, for its icon. */
  kind?: string
}

export type Undo = {
  kind: 'approve' | 'reject'
  key: string
  source: SuggestionSource
  calendar_id?: string | null
  event_key?: string | null
  month?: string
  /** Issued by the server; undo works from this, once, for a day. */
  token?: string
}

type Result = { ok: boolean; error?: string; items?: Suggestion[]; undo?: Undo }

export const SOURCE_LABEL: Record<SuggestionSource, string> = {
  yours: 'Your suggestion',
  scout: 'Found by the scout',
  date: 'From your important dates',
}

async function call(method: string, path: string, body?: unknown, name?: string): Promise<Result> {
  try {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (name) headers['X-Actor-Display-Name'] = name
    const res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (res.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
      return { ok: false, error: 'Please sign in again.' }
    }
    const j = (await res.json().catch(() => ({}))) as Result
    if (!res.ok || j.ok === false) return { ok: false, error: j.error || `Something went wrong (${res.status}).` }
    return j
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.' }
  }
}

const base = (brand: string) => `/api/calendar-suggestions/${encodeURIComponent(brand)}`

export const fetchSuggestions = (brand: string, month: string) =>
  call('GET', `${base(brand)}?month=${encodeURIComponent(month)}`)

export const approveSuggestion = (brand: string, month: string, key: string, name: string, pillars: string[] = []) =>
  call('POST', `${base(brand)}/approve`, { month, key, pillars }, name)

export type PillarOption = { pillar_id: string; name?: string }

/** The brand's pillars, for the picker on a card. Empty when they cannot be read. */
export async function fetchPillars(brand: string): Promise<PillarOption[]> {
  try {
    const res = await fetch(`/api/calendar/context/${encodeURIComponent(brand)}`, { credentials: 'same-origin' })
    const j = (await res.json()) as { pillars?: Array<{ pillar_id?: string; name?: string }> }
    return (j.pillars || []).filter((p): p is PillarOption => Boolean(p.pillar_id))
  } catch {
    return []
  }
}

export const rejectSuggestion = (brand: string, month: string, key: string, name: string) =>
  call('POST', `${base(brand)}/reject`, { month, key }, name)

export const undoSuggestion = (brand: string, undo: Undo) => call('POST', `${base(brand)}/undo`, { undo })

/** Suggestions grouped by the day they are drawn on. */
export function groupByDay(items: Suggestion[]): Record<string, Suggestion[]> {
  const out: Record<string, Suggestion[]> = {}
  for (const s of items) (out[s.date] ||= []).push(s)
  return out
}

/** "14 Mar" or "14 – 21 Mar" for the hover card. */
export function spanLabel(date: string, end: string): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const part = (iso: string) => {
    const [, m, d] = iso.slice(0, 10).split('-').map(Number)
    return { d, m: months[m - 1] }
  }
  const a = part(date)
  if (!end || end === date) return `${a.d} ${a.m}`
  const b = part(end)
  return a.m === b.m ? `${a.d} – ${b.d} ${b.m}` : `${a.d} ${a.m} – ${b.d} ${b.m}`
}

/** What the undo bar says after an action. */
export function undoMessage(kind: Undo['kind'], title: string): string {
  return kind === 'approve' ? `Added “${title}” to the calendar.` : `Removed “${title}”.`
}

const SHOW_KEY = 'cos_month_suggestions'
const SHOW_PLANS_KEY = 'cos_month_plan_steps'

export function readShowSuggestions(): boolean {
  try {
    return window.localStorage.getItem(SHOW_KEY) !== 'off'
  } catch {
    return true
  }
}

export function readShowPlanSteps(): boolean {
  try {
    return window.localStorage.getItem(SHOW_PLANS_KEY) !== 'off'
  } catch {
    return true
  }
}

export function saveShowPlanSteps(on: boolean): void {
  try {
    window.localStorage.setItem(SHOW_PLANS_KEY, on ? 'on' : 'off')
  } catch {
    /* private window: the choice lasts until reload */
  }
}

export function saveShowSuggestions(on: boolean): void {
  try {
    window.localStorage.setItem(SHOW_KEY, on ? 'on' : 'off')
  } catch {
    /* private window: the choice lasts until reload */
  }
}
