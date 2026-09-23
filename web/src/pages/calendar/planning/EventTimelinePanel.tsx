import { useMemo, useState } from 'react'
import { PIN_COLORS } from '../../../lib/planning'
import type { PlanningTimeline, PlanningTimelineEvent } from '../../../lib/planningTypes'
import { EventDetail } from './EventDetail'
import type { PlanningEventDetail } from '../../../lib/planningTypes'

const MONTH_NAMES = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const TIER_ORDER = ['A-PIN', 'B-PIN', 'C-PIN']

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
  const [shoppingOnly, setShoppingOnly] = useState(false)
  const yearInt = parseInt(year, 10)

  const { visibleEvents, skippedCount } = useMemo(() => {
    if (!timeline?.ok || !timeline.events) {
      return { visibleEvents: [] as PlanningTimelineEvent[], skippedCount: 0 }
    }
    let skipped = 0
    const base = timeline.events.filter((ev) => {
      const m = timelineBarMetrics(ev, yearInt)
      if (!m) {
        skipped += 1
        return false
      }
      return true
    })
    const visible = shoppingOnly ? base.filter((e) => e.shopping_moment) : base
    return { visibleEvents: visible, skippedCount: skipped }
  }, [timeline, yearInt, shoppingOnly])

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

  return (
    <section className="glass space-y-4 rounded-2xl border border-white/10 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold">Event timeline · {year}</h2>
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

      <div>
        <p className="mb-2 text-[9px] font-bold tracking-widest text-tx3 uppercase">Always on</p>
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
                  <span className="text-[10px] font-bold tracking-wide uppercase" style={{ color: c.fg }}>
                    {tier}
                  </span>
                  <span className="text-[10px] text-tx3">
                    · {tierEvents.length} {tierEvents.length === 1 ? 'event' : 'events'}
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
                      className="relative mb-1 block h-8 w-full cursor-pointer overflow-hidden rounded-md bg-bg2 text-left transition-colors hover:border-yel/40"
                      onClick={() => onOpenEvent(ev.id)}
                    >
                      <div className="pointer-events-none absolute top-0 bottom-0 left-2 z-10 flex max-w-[140px] items-center">
                        <span className="truncate text-[11px] font-bold">
                          {ev.name}
                          {shop}
                        </span>
                      </div>
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
