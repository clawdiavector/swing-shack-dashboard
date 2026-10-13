// Approved dates that are close and have no plan or content.

export type AlertLevel = 'scream' | 'warn'
export type AlertState = 'no_plan' | 'plan_draft' | 'plan_approved'

export type CalendarAlert = {
  event_key: string
  name: string
  date: string
  days: number
  /** Started and not yet over. */
  in_progress?: boolean
  ends?: string
  tier: string
  level: AlertLevel
  state: AlertState
  brief_id: string | null
  plan_id: string | null
  brand_id: string
  kind?: string
  message: string
}

export type AlertsResult = { ok: boolean; error?: string; alerts: CalendarAlert[]; screaming: number }

/** Brand ids to ask about: one brand, or '' for all of them. */
export async function fetchAlerts(brand: string): Promise<AlertsResult> {
  try {
    const res = await fetch(`/api/calendar-alerts?brand=${encodeURIComponent(brand || 'all')}`, {
      credentials: 'same-origin',
    })
    if (res.status === 401) return { ok: false, error: 'auth required', alerts: [], screaming: 0 }
    const j = (await res.json().catch(() => ({}))) as Partial<AlertsResult>
    if (!res.ok || j.ok === false) {
      return { ok: false, error: j.error || `Something went wrong (${res.status}).`, alerts: [], screaming: 0 }
    }
    return { ok: true, alerts: j.alerts || [], screaming: j.screaming || 0 }
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.', alerts: [], screaming: 0 }
  }
}

/** The one line across the top: how loud, and how many. */
export function alertHeadline(alerts: CalendarAlert[]): string {
  const loud = alerts.filter((a) => a.level === 'scream').length
  if (!alerts.length) return ''
  const dates = (n: number) => `${n} approved date${n === 1 ? '' : 's'}`
  if (loud) {
    return `${dates(loud)} ${loud === 1 ? 'is' : 'are'} close and not ready`
  }
  return `${dates(alerts.length)} coming up with nothing ready yet`
}

/** What the row's button does, by where the date has got to. */
export function alertAction(state: AlertState): string {
  return state === 'no_plan' ? 'Make a plan' : 'Open the plan'
}

const CHANGED = 'cos:alerts-changed'

/** Tell anything showing alerts (the menu dot, the banners) to look again. */
export function notifyAlertsChanged(): void {
  window.dispatchEvent(new Event(CHANGED))
}

/** Listen for notifyAlertsChanged; returns the function that stops listening. */
export function onAlertsChanged(cb: () => void): () => void {
  window.addEventListener(CHANGED, cb)
  return () => window.removeEventListener(CHANGED, cb)
}

/** What the menu dot shows: red, with how many are close and not ready, and
 *  nothing at all otherwise. Dates that are only coming up stay in the banners,
 *  so the dot never sits there for weeks. */
export function dotState(alerts: CalendarAlert[]): { count: number; tone: 'scream' | 'none' } {
  const loud = alerts.filter((a) => a.level === 'scream').length
  return loud ? { count: loud, tone: 'scream' } : { count: 0, tone: 'none' }
}
