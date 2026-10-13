import { Loader2, Siren } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  alertAction,
  alertHeadline,
  fetchAlerts,
  notifyAlertsChanged,
  type CalendarAlert,
} from '../../../lib/calendarAlerts'
import { EventTypeIcon } from '../../../components/EventTypeIcon'
import { planFromEvent } from '../../../lib/plan'

/** The loud one: approved dates that are close and have no plan or content.
 *  Shown at the top of Today and Plan. Says nothing when all is ready. */
export function AlertBanner({ brandId = '', refreshKey = 0 }: { brandId?: string; refreshKey?: number }) {
  const [alerts, setAlerts] = useState<CalendarAlert[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [done, setDone] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    void fetchAlerts(brandId).then((r) => {
      if (!cancelled && r.ok) setAlerts(r.alerts)
    })
    return () => {
      cancelled = true
    }
  }, [brandId, refreshKey, tick])

  const makePlan = useCallback(async (a: CalendarAlert) => {
    setBusy(a.event_key)
    setErrors((e) => ({ ...e, [a.event_key]: '' }))
    const r = await planFromEvent(a.brand_id, a.event_key)
    setBusy(null)
    if (!r.ok) {
      setErrors((e) => ({ ...e, [a.event_key]: r.error || 'Could not make the plan.' }))
      return
    }
    setDone((d) => ({ ...d, [a.event_key]: 'Draft plan made. Open it in Plan, check it, then approve.' }))
    setTick((t) => t + 1)
    notifyAlertsChanged()
  }, [])

  if (!alerts.length) return null
  const loud = alerts.some((a) => a.level === 'scream')
  const tone = loud ? 'border-red/60 bg-red/10' : 'border-yel/50 bg-yel/10'

  return (
    <section
      role="alert"
      data-testid="alert-banner"
      data-level={loud ? 'scream' : 'warn'}
      className={`space-y-3 rounded-xl border-2 px-4 py-3 ${tone}`}
    >
      <p className={`flex items-center gap-2 text-sm font-extrabold tracking-wide uppercase ${loud ? 'text-red' : 'text-yel'}`}>
        <Siren className={`h-5 w-5 ${loud ? 'motion-safe:animate-pulse' : ''}`} />
        {alertHeadline(alerts)}
      </p>
      <ul className="space-y-2">
        {alerts.map((a) => (
          <li
            key={`${a.brand_id}:${a.event_key}`}
            data-testid="alert-row"
            data-level={a.level}
            className="flex flex-wrap items-center gap-x-3 gap-y-1"
          >
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider uppercase ${
                a.level === 'scream' ? 'bg-red text-bg' : 'bg-yel/30 text-yel'
              }`}
            >
              {a.days === 0 ? 'today' : `${a.days}d`}
            </span>
            <EventTypeIcon kind={a.kind} />
            <span className="min-w-0 flex-1 text-sm font-semibold text-tx">{a.message}</span>
            {done[a.event_key] ? (
              <span className="text-xs text-tx2">{done[a.event_key]}</span>
            ) : a.state === 'no_plan' ? (
              <button
                type="button"
                disabled={busy === a.event_key}
                onClick={() => void makePlan(a)}
                data-testid="alert-make-plan"
                className="inline-flex items-center gap-1.5 rounded-full border border-yel/50 bg-yel/20 px-3 py-1 text-xs font-semibold text-yel hover:bg-yel/30 disabled:opacity-60"
              >
                {busy === a.event_key ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                {alertAction(a.state)}
              </button>
            ) : null}
            {(a.state !== 'no_plan' || done[a.event_key]) && (
              <Link
                to="/calendar/lanes"
                className="rounded-full border border-bd px-3 py-1 text-xs font-semibold text-tx2 hover:text-tx"
              >
                {done[a.event_key] ? 'Open Plan' : alertAction(a.state)}
              </Link>
            )}
            {errors[a.event_key] ? <span className="w-full text-xs text-red">{errors[a.event_key]}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
