import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  PIN_COLORS,
  PLANNING_TIMELINE_YEAR_MAX,
  PLANNING_TIMELINE_YEAR_MIN,
  clampPlanningTimelineYear,
  formatTimelineWindowLabel,
  localTodayIso,
  shiftPlanningTimelineYear,
} from '../../../lib/planning'
import type { PlanningTimeline, PlanningTimelineEvent } from '../../../lib/planningTypes'
import { EventDetail } from './EventDetail'
import type { PlanningEventDetail } from '../../../lib/planningTypes'

const MONTH_NAMES = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const TIER_ORDER = ['A-PIN', 'B-PIN', 'C-PIN']

const ZOOM_OPTIONS = [
  { id: '30', label: '30D', days: 30, hint: 'Immediate / tactical' },
  { id: '90', label: '90D', days: 90, hint: 'Default planning' },
  { id: '182', label: '6M', days: 182, hint: 'Medium-term' },
  { id: '365', label: '12M', days: 365, hint: 'Full strategic year' },
] as const

type ZoomId = (typeof ZOOM_OPTIONS)[number]['id']

function zoomIdToDays(z: string | null): number {
  const found = ZOOM_OPTIONS.find((o) => o.id === z)
  return found ? found.days : 90
}

function timelineBarMetrics(
  ev: PlanningTimelineEvent,
  yearInt: number,
): { sPct: number; widthPct: number; peakPct: number | null } | null {
  const startDate = ev.start || ev.planning_start
  const endDate = ev.end || ev.public_peak
  if (!startDate || !endDate) return null
  const yearStart = new Date(yearInt, 0, 1).getTime()
  const yearEnd = new Date(yearInt, 11, 31).getTime()
  const yearMs = yearEnd - yearStart
  const sDate = new Date(`${startDate}T00:00:00`).getTime()
  const eDate = new Date(`${endDate}T00:00:00`).getTime()
  const sPct = Math.max(0, ((sDate - yearStart) / yearMs) * 100)
  const ePct = Math.min(100, ((eDate - yearStart) / yearMs) * 100)
  const widthPct = Math.max(1.5, ePct - sPct)
  let peakPct: number | null = null
  if (ev.public_peak) {
    peakPct = ((new Date(`${ev.public_peak}T00:00:00`).getTime() - yearStart) / yearMs) * 100
  }
  return { sPct, widthPct, peakPct }
}

export function EventTimelinePanel({
  brand,
  year,
  timeline,
  eventDetail,
  onOpenEvent,
  onCloseEvent,
}: {
  brand: string
  year: string
  timeline: PlanningTimeline | null
  eventDetail: PlanningEventDetail | null
  onOpenEvent: (id: string) => void
  onCloseEvent: () => void
}) {
  const [params, setParams] = useSearchParams()
  const viewParam = params.get('view')
  const zoomId: ZoomId =
    viewParam === '30' || viewParam === '90' || viewParam === '182' || viewParam === '365'
      ? viewParam
      : '90'
  const zoomDays = zoomIdToDays(zoomId)

  // offset = days from today that the visible window starts at. 0 = anchored on today.
  const [offsetDays, setOffsetDays] = useState(0)

  const setZoom = useCallback(
    (id: ZoomId) => {
      setOffsetDays(0)
      const p = new URLSearchParams(params)
      p.set('view', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const [shoppingOnly, setShoppingOnly] = useState(false)
  const yearInt = parseInt(year, 10)
  const todayIso = useMemo(() => localTodayIso(), [])
  const isFullYearZoom = zoomDays >= 365
  const canPrevYear = yearInt > PLANNING_TIMELINE_YEAR_MIN
  const canNextYear = yearInt < PLANNING_TIMELINE_YEAR_MAX

  const goPrev = useCallback(() => {
    if (isFullYearZoom) {
      const prev = shiftPlanningTimelineYear(yearInt, -1)
      if (prev == null) return
      const p = new URLSearchParams(params)
      p.set('year', String(prev))
      setParams(p, { replace: true })
      return
    }
    setOffsetDays((d) => d - zoomDays)
  }, [isFullYearZoom, yearInt, zoomDays, params, setParams])

  const goNext = useCallback(() => {
    if (isFullYearZoom) {
      const next = shiftPlanningTimelineYear(yearInt, 1)
      if (next == null) return
      const p = new URLSearchParams(params)
      p.set('year', String(next))
      setParams(p, { replace: true })
      return
    }
    setOffsetDays((d) => d + zoomDays)
  }, [isFullYearZoom, yearInt, zoomDays, params, setParams])

  const goToday = useCallback(() => {
    setOffsetDays(0)
    if (!isFullYearZoom) return
    const p = new URLSearchParams(params)
    p.set('year', String(clampPlanningTimelineYear(parseInt(todayIso.slice(0, 4), 10))))
    setParams(p, { replace: true })
  }, [isFullYearZoom, todayIso, params, setParams])

  const navPrevDisabled = isFullYearZoom && !canPrevYear
  const navNextDisabled = isFullYearZoom && !canNextYear

  const todayRef = useRef<HTMLDivElement | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)

  // After every render, scroll the viewport so the visible window is anchored on
  // (today + offset). At 12M (full year) nothing scrolls; at narrower zooms we
  // place today at the left edge so upcoming events dominate.
  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    if (zoomDays >= 365) {
      vp.scrollLeft = 0
      return
    }
    const yearStart = new Date(yearInt, 0, 1).getTime()
    const yearMs = new Date(yearInt, 11, 31).getTime() - yearStart
    const todayMs = new Date(`${todayIso}T00:00:00`).getTime()
    const todayPct = Math.max(0, Math.min(1, (todayMs - yearStart) / yearMs))
    const canvasW = vp.scrollWidth
    const target = Math.round(todayPct * canvasW + offsetDays * (canvasW / 365))
    const max = vp.scrollWidth - vp.clientWidth
    vp.scrollLeft = Math.max(0, Math.min(max, target))
  }, [timeline, zoomDays, offsetDays, yearInt, todayIso])

  const visibleEvents: PlanningTimelineEvent[] = useMemo(() => {
    if (!timeline?.ok || !timeline.events) {
      return [] as PlanningTimelineEvent[]
    }
    const base = timeline.events.filter((ev) => {
      const m = timelineBarMetrics(ev, yearInt)
      return !!m
    })
    return shoppingOnly ? base.filter((e) => e.shopping_moment) : base
  }, [timeline, yearInt, shoppingOnly])

  const skippedCount: number = useMemo(() => {
    if (!timeline?.ok || !timeline.events) return 0
    return timeline.events.reduce((n, ev) => {
      const m = timelineBarMetrics(ev, yearInt)
      return m ? n : n + 1
    }, 0)
  }, [timeline, yearInt])

  if (!timeline?.ok) {
    return (
      <section className="glass rounded-2xl border border-white/10 p-4">
        <p className="text-sm text-tx3">
          No event spine loaded for {year} on {brand}. Timeline data is only available for Stick
          today.
        </p>
      </section>
    )
  }

  const pillars = timeline.always_on_pillars || []
  const byTier: Record<string, PlanningTimelineEvent[]> = {}
  for (const ev of visibleEvents) {
    const t = ev.tier || 'C-PIN'
    if (!byTier[t]) byTier[t] = []
    byTier[t].push(ev)
  }

  const windowLabel = formatTimelineWindowLabel({
    zoomDays,
    yearInt,
    offsetDays,
    todayIso,
  })

  // Canvas width as % of viewport. 30D = 1217%, 90D = 405%, 6M = 200%, 12M = 100%.
  const canvasWidthPct = (365 / zoomDays) * 100
  const compact = zoomDays >= 182
  const ultraCompact = zoomDays >= 365
  const rowH = ultraCompact ? 'h-[22px]' : compact ? 'h-7' : 'h-8'
  const labelW = ultraCompact ? 0 : compact ? 100 : 140

  // TODAY marker position (as % of canvas / year)
  const yearStartMs = new Date(yearInt, 0, 1).getTime()
  const yearMs = new Date(yearInt, 11, 31).getTime() - yearStartMs
  const todayPctOfYear =
    ((new Date(`${todayIso}T00:00:00`).getTime() - yearStartMs) / yearMs) * 100

  return (
    <section className="glass space-y-4 rounded-2xl border border-white/10 p-4">
      {/* Zoom selector + filter */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold">Event timeline · {year}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-bg1 p-1">
            {ZOOM_OPTIONS.map((opt) => {
              const active = opt.id === zoomId
              return (
                <button
                  key={opt.id}
                  type="button"
                  title={opt.hint}
                  onClick={() => setZoom(opt.id)}
                  data-testid={`zoom-${opt.id}`}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    active
                      ? 'bg-yel text-bg border border-yel'
                      : 'bg-bg2 text-tx border border-bd hover:border-yel/60'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </span>
          <button
            type="button"
            onClick={() => setShoppingOnly((v) => !v)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
              shoppingOnly
                ? 'border-yel bg-yel text-bg'
                : 'border-bd bg-bg2 text-tx hover:border-yel'
            }`}
          >
            Shopping moments
          </button>
        </div>
      </div>

      {/* Prev / Today / Next + window label */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-bg2 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={goPrev}
            disabled={navPrevDisabled}
            title={
              isFullYearZoom
                ? 'Previous calendar year (matches Year selector)'
                : 'Earlier window — scrolls timeline left'
            }
            data-testid="nav-prev"
            className="rounded border border-bd bg-bg1 px-2.5 py-1 text-sm font-semibold text-tx hover:border-yel/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ‹ Prev
          </button>
          <button
            type="button"
            onClick={goToday}
            data-testid="nav-today"
            className="rounded border border-bd bg-bg1 px-2.5 py-1 text-[11px] font-bold tracking-wider text-tx hover:border-yel/60"
          >
            ⊕ TODAY
          </button>
          <button
            type="button"
            onClick={goNext}
            disabled={navNextDisabled}
            title={
              isFullYearZoom
                ? 'Next calendar year (matches Year selector)'
                : 'Later window — scrolls timeline right'
            }
            data-testid="nav-next"
            className="rounded border border-bd bg-bg1 px-2.5 py-1 text-sm font-semibold text-tx hover:border-yel/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next ›
          </button>
        </div>
        <div className="text-[11px] font-semibold tracking-wider text-tx2 uppercase">
          Window: {windowLabel}{' '}
          <span className="font-normal text-tx3">
            · {isFullYearZoom ? 'calendar year' : `${zoomDays} days`}
          </span>
        </div>
      </div>

      {/* Scrollable viewport — full year canvas, anchored to (today + offset). */}
      <div
        ref={viewportRef}
        className="relative overflow-x-auto overflow-y-visible"
        style={{ WebkitOverflowScrolling: 'touch' }}
      >
        <div
          style={{ width: `${canvasWidthPct.toFixed(2)}%` }}
          className="relative pb-2"
        >
          {/* Month axis */}
          <div className="relative mb-2 h-[18px] border-b border-bd">
            {MONTH_NAMES.map((name, m) => {
              const leftPct = (m / 12) * 100
              return (
                <div key={name}>
                  <div
                    className="absolute top-0 text-[9px] tracking-wider text-tx3 uppercase"
                    style={{ left: `${leftPct}%` }}
                  >
                    {name}
                  </div>
                  {m % 3 === 0 && m > 0 ? (
                    <div
                      className="absolute top-3.5 bottom-0 w-px bg-bd/50"
                      style={{ left: `${leftPct}%` }}
                      aria-hidden
                    />
                  ) : null}
                </div>
              )
            })}
          </div>

          {/* Always on */}
          <div className="mb-4">
            <p className="mb-2 text-[9px] font-bold tracking-widest text-tx3 uppercase">
              Always on
            </p>
            {pillars.map((p, idx) => {
              const colors = ['#f0a030', '#14b8a6', '#f0a030']
              const c = colors[idx % colors.length]
              return (
                <div
                  key={p.name || idx}
                  className="relative mb-1 flex h-9 items-center overflow-hidden rounded-md bg-bg2 px-3"
                >
                  <div
                    className="absolute inset-0 opacity-30"
                    style={{
                      background: `repeating-linear-gradient(90deg, transparent 0, transparent 7px, ${c}15 7px, ${c}15 14px)`,
                    }}
                    aria-hidden
                  />
                  <p className="relative z-10 text-xs font-bold" style={{ color: c }}>
                    {p.name}{' '}
                    <span className="ml-2 font-normal text-tx3">
                      {(p.current_push_summary || p.purpose || '').slice(0, 90)}
                    </span>
                  </p>
                </div>
              )
            })}
          </div>

          {/* Events / commercial pushes */}
          <div>
            <p className="mb-2 text-[9px] font-bold tracking-widest text-tx3 uppercase">
              Events / commercial pushes
            </p>
            {visibleEvents.length === 0 ? (
              <p className="text-sm text-tx3">
                No events for {year}
                {shoppingOnly ? ' in shopping moments' : ''}.
              </p>
            ) : (
              TIER_ORDER.map((tier) => {
                const tierEvents = byTier[tier]
                if (!tierEvents?.length) return null
                const c = PIN_COLORS[tier]
                return (
                  <div key={tier} className="mb-3">
                    <div className="mb-1 flex items-center gap-2">
                      <span
                        className="inline-block h-1.5 w-1.5 rounded-full"
                        style={{ background: c.bar }}
                      />
                      <span
                        className="text-[10px] font-bold tracking-wide uppercase"
                        style={{ color: c.fg }}
                      >
                        {tier}
                      </span>
                      <span className="text-[10px] text-tx3">
                        · {tierEvents.length}{' '}
                        {tierEvents.length === 1 ? 'event' : 'events'}
                      </span>
                    </div>
                    {tierEvents.map((ev) => {
                      const m = timelineBarMetrics(ev, yearInt)
                      if (!m) return null
                      const shop = ev.shopping_moment ? ' 🛍' : ''
                      return (
                        <button
                          key={ev.id}
                          type="button"
                          className={`relative mb-1 block w-full cursor-pointer overflow-hidden rounded-md bg-bg2 text-left transition-colors hover:border-yel/40 ${rowH}`}
                          onClick={() => onOpenEvent(ev.id)}
                        >
                          {!ultraCompact ? (
                            <div
                              className="pointer-events-none absolute top-0 bottom-0 left-2 z-10 flex items-center"
                              style={{ maxWidth: `${labelW}px` }}
                            >
                              <span className="truncate text-[11px] font-bold">
                                {ev.name}
                                {shop}
                              </span>
                            </div>
                          ) : null}
                          <div
                            className="absolute top-1.5 bottom-1.5 flex items-center rounded px-2"
                            style={{
                              left: `${m.sPct}%`,
                              width: `${m.widthPct}%`,
                              background: c.barBg,
                              borderLeft: `3px solid ${c.bar}`,
                            }}
                          >
                            <span
                              className="truncate text-[10px] font-bold"
                              style={{ color: c.fg }}
                            >
                              {ev.name}
                              {shop}
                            </span>
                          </div>
                          {m.peakPct != null ? (
                            <>
                              <div
                                className="absolute top-0 bottom-0 w-0.5 opacity-70"
                                style={{ left: `${m.peakPct}%`, background: c.fg }}
                                aria-hidden
                              />
                              <div
                                className="absolute -top-0.5 h-2 w-2 -translate-x-1/2 rounded-full shadow-[0_0_0_2px_var(--color-bg)]"
                                style={{ left: `${m.peakPct}%`, background: c.fg }}
                                aria-hidden
                              />
                            </>
                          ) : null}
                        </button>
                      )
                    })}
                  </div>
                )
              })
            )}
          </div>

          {/* TODAY marker — vertical red line at today's position in the year. */}
          <div
            ref={todayRef}
            data-testid="today-marker"
            className="pointer-events-none absolute top-0 bottom-0 z-10"
            style={{
              left: `${todayPctOfYear}%`,
              width: '2px',
              background: '#ef4444',
              boxShadow: '0 0 0 1px rgba(239,68,68,.3)',
            }}
            aria-hidden
          />
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 rounded bg-red-500 px-1.5 py-0.5 text-[10px] font-bold whitespace-nowrap text-white"
            style={{ left: `${todayPctOfYear}%`, top: '0' }}
            data-testid="today-label"
          >
            ⊕ TODAY
          </div>
        </div>
      </div>

      {skippedCount > 0 ? (
        <p className="text-xs text-tx3">
          {skippedCount} {skippedCount === 1 ? 'event' : 'events'} without dates (hidden from
          timeline).
        </p>
      ) : null}

      <div className="flex flex-wrap gap-4 text-[10px] text-tx3">
        <span>
          <span className="mr-1 inline-block h-2 w-3.5 rounded-sm bg-[#f0a030] align-middle" />
          A-PIN major commercial push (6–8wk runway)
        </span>
        <span>
          <span className="mr-1 inline-block h-2 w-3.5 rounded-sm bg-[#14b8a6] align-middle" />
          B-PIN content week (3–4wk)
        </span>
        <span>
          <span className="mr-1 inline-block h-2 w-3.5 rounded border border-[#94a3b8] align-middle" />
          C-PIN light hook (&lt;2wk)
        </span>
      </div>

      <EventDetail data={eventDetail} onClose={onCloseEvent} />
    </section>
  )
}
