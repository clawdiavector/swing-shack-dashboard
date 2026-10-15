import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { dotState, fetchAlertsShared, onAlertsChanged, type CalendarAlert } from '../lib/calendarAlerts'
import { useBrand, useBrandScope } from './BrandSwitch'

const REFRESH_MS = 5 * 60 * 1000

/** A dot on the Plan menu item: red, with a count, when an approved date is
 *  close and has nothing ready. Nothing otherwise; dates that are only coming
 *  up show in the banners, not here. */
export function PlanAlertDot({ className = '' }: { className?: string }) {
  const { brandId } = useBrand()
  const { isAll } = useBrandScope()
  const loc = useLocation()
  const [alerts, setAlerts] = useState<CalendarAlert[]>([])
  const [tick, setTick] = useState(0)
  const brand = isAll ? '' : brandId || ''

  useEffect(() => onAlertsChanged(() => setTick((t) => t + 1)), [])

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), REFRESH_MS)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    let cancelled = false
    void fetchAlertsShared(brand).then((r) => {
      if (!cancelled && r.ok) setAlerts(r.alerts)
    })
    return () => {
      cancelled = true
    }
  }, [brand, loc.pathname, tick])

  const { count, tone } = dotState(alerts)
  if (tone === 'none') return null
  const label = `${count} approved ${count === 1 ? 'date is' : 'dates are'} close and not ready`
  return (
    <span
      role="img"
      data-testid="plan-alert-dot"
      data-tone={tone}
      aria-label={label}
      title={label}
      className={`pointer-events-auto absolute grid min-h-[14px] min-w-[14px] place-items-center rounded-full bg-red px-1 text-[9px] leading-none font-extrabold text-bg motion-safe:animate-pulse ${className}`}
    >
      {count > 9 ? '9+' : count}
    </span>
  )
}
