import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  alertAction,
  alertHeadline,
  clearSharedAlerts,
  dotState,
  fetchAlertsShared,
  notifyAlertsChanged,
  planPageHref,
  type CalendarAlert,
} from './calendarAlerts'

const a = (level: 'scream' | 'warn'): CalendarAlert => ({
  event_key: 'k',
  name: 'Heritage Day',
  date: '2026-10-20',
  days: 7,
  tier: 'A-PIN',
  level,
  state: 'no_plan',
  brief_id: null,
  plan_id: null,
  brand_id: 'stick',
  message: '',
})

describe('alertHeadline', () => {
  it('is empty with nothing to say', () => {
    expect(alertHeadline([])).toBe('')
  })
  it('counts only the loud ones when any are loud', () => {
    expect(alertHeadline([a('scream'), a('warn')])).toBe('1 approved date is close and not ready')
    expect(alertHeadline([a('scream'), a('scream')])).toBe('2 approved dates are close and not ready')
  })
  it('is calmer when none are loud', () => {
    expect(alertHeadline([a('warn')])).toBe('1 approved date coming up with nothing ready yet')
  })
})

describe('alertAction', () => {
  it('makes a plan only when there is none', () => {
    expect(alertAction('no_plan')).toBe('Make a plan')
    expect(alertAction('plan_draft')).toBe('Open the plan')
    expect(alertAction('plan_approved')).toBe('Open the plan')
  })
})

describe('planPageHref', () => {
  it('opens the list with the date selected, not the bare Plan page', () => {
    expect(planPageHref({ event_key: 'swing-shack:halloween:2026-10-31' })).toBe(
      '/calendar/lanes?tab=list&event=swing-shack%3Ahalloween%3A2026-10-31',
    )
  })
})

describe('dotState', () => {
  it('is quiet with nothing and with only warnings, and counts only the red ones', () => {
    expect(dotState([])).toEqual({ count: 0, tone: 'none' })
    expect(dotState([a('warn'), a('warn')])).toEqual({ count: 0, tone: 'none' })
    expect(dotState([a('warn'), a('scream')])).toEqual({ count: 1, tone: 'scream' })
    expect(dotState([a('scream'), a('scream')])).toEqual({ count: 2, tone: 'scream' })
  })
})

describe('fetchAlertsShared', () => {
  const ok = (n: number) =>
    new Response(JSON.stringify({ ok: true, alerts: [], screaming: n }), { status: 200 })

  beforeEach(() => {
    clearSharedAlerts()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shares one request between callers, then asks again once the time is up', async () => {
    const f = vi.fn(async () => ok(1))
    vi.stubGlobal('fetch', f)
    const [a, b, c] = await Promise.all([
      fetchAlertsShared('stick', 1000),
      fetchAlertsShared('stick', 1005),
      fetchAlertsShared('stick', 1010),
    ])
    expect(f).toHaveBeenCalledTimes(1)
    expect(a).toBe(b)
    expect(b).toBe(c)
    await fetchAlertsShared('stick', 1000 + 31_000)
    expect(f).toHaveBeenCalledTimes(2)
  })

  it('keeps brands apart, and treats "" as all brands', async () => {
    const f = vi.fn(async () => ok(0))
    vi.stubGlobal('fetch', f)
    await fetchAlertsShared('stick', 1)
    await fetchAlertsShared('swing-shack', 1)
    await fetchAlertsShared('', 1)
    await fetchAlertsShared('all', 2)
    expect(f).toHaveBeenCalledTimes(3)
  })

  it('does not keep a failure, so the next ask tries again', async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 500 }))
      .mockResolvedValue(ok(2))
    vi.stubGlobal('fetch', f)
    const bad = await fetchAlertsShared('stick', 1)
    expect(bad.ok).toBe(false)
    const good = await fetchAlertsShared('stick', 2)
    expect(good.ok).toBe(true)
    expect(f).toHaveBeenCalledTimes(2)
  })

  it('a change forgets what was shared', async () => {
    const f = vi.fn(async () => ok(1))
    vi.stubGlobal('fetch', f)
    await fetchAlertsShared('stick', 1)
    notifyAlertsChanged()
    await fetchAlertsShared('stick', 2)
    expect(f).toHaveBeenCalledTimes(2)
  })
})
