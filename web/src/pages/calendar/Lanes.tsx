import { Map } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { ClassicLink, Tip } from '../../components/ui'
import {
  fetchPlanningBigIdea,
  fetchPlanningEvent,
  fetchPlanningMonth,
  fetchPlanningRightNow,
  fetchPlanningTimeline,
} from '../../lib/api'
import {
  getCachedPlanningEvent,
  planningEventCacheKey,
  setCachedPlanningEvent,
} from '../../lib/planning'
import type {
  PlanningBigIdeaResponse,
  PlanningEventDetail,
  PlanningMonthView,
  PlanningRightNow,
  PlanningTimeline,
} from '../../lib/planningTypes'
import { EventDetail } from './planning/EventDetail'
import { EventTimelinePanel } from './planning/EventTimelinePanel'
import { LaneMonthPanel } from './planning/LaneMonthPanel'
import { PlanningHero } from './planning/PlanningHero'
import { RightNowStrip } from './planning/RightNowStrip'

type LanesTab = 'strategy' | 'timeline' | 'month' | 'parked'

const TAB_OPTIONS = [
  { id: 'strategy', label: 'Strategy' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'month', label: 'Month' },
  { id: 'parked', label: 'Parked posts' },
]

const VALID_TABS = new Set<string>(TAB_OPTIONS.map((t) => t.id))

async function safeLoad<T>(fn: () => Promise<T>): Promise<T | { ok: false }> {
  try {
    return await fn()
  } catch {
    return { ok: false }
  }
}

function panelFailed(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object') return true
  const o = payload as { ok?: boolean }
  return o.ok === false
}

export function Lanes() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params, setParams] = useSearchParams()
  const rawTab = params.get('tab') || 'strategy'
  const tab: LanesTab = VALID_TABS.has(rawTab) ? (rawTab as LanesTab) : 'strategy'

  const monthParam =
    params.get('month') ||
    `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
  const yearParam = params.get('year') || String(new Date().getFullYear())

  const [bigIdea, setBigIdea] = useState<PlanningBigIdeaResponse | null>(null)
  const [rightNow, setRightNow] = useState<PlanningRightNow | null>(null)
  const [monthView, setMonthView] = useState<PlanningMonthView | null>(null)
  const [timeline, setTimeline] = useState<PlanningTimeline | null>(null)
  const [loading, setLoading] = useState(false)
  const [eventDetail, setEventDetail] = useState<PlanningEventDetail | null>(null)

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const setMonthParam = useCallback(
    (next: string) => {
      const p = new URLSearchParams(params)
      p.set('month', next)
      p.set('tab', 'month')
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  useEffect(() => {
    if (!scopeBrand) return
    let gone = false
    setLoading(true)
    Promise.all([
      safeLoad(() => fetchPlanningBigIdea(scopeBrand)),
      safeLoad(() => fetchPlanningRightNow(scopeBrand)),
      safeLoad(() => fetchPlanningMonth(scopeBrand, monthParam)),
      safeLoad(() => fetchPlanningTimeline(scopeBrand, yearParam)),
    ]).then(([bi, rn, mo, tl]) => {
      if (gone) return
      setBigIdea(bi as PlanningBigIdeaResponse)
      setRightNow(rn as PlanningRightNow)
      setMonthView(mo as PlanningMonthView)
      setTimeline(tl as PlanningTimeline)
      setLoading(false)
    })
    return () => {
      gone = true
    }
  }, [scopeBrand, monthParam, yearParam])

  const openEvent = useCallback(
    async (eventId: string) => {
      if (!scopeBrand) return
      const cacheKey = planningEventCacheKey(scopeBrand, eventId)
      const cached = getCachedPlanningEvent(cacheKey) as PlanningEventDetail | undefined
      if (cached?.ok) {
        setEventDetail(cached)
        return
      }
      const r = await safeLoad(() => fetchPlanningEvent(scopeBrand, eventId))
      if (r && typeof r === 'object' && (r as PlanningEventDetail).ok !== false) {
        const detail = r as PlanningEventDetail
        setCachedPlanningEvent(cacheKey, detail)
        setEventDetail(detail)
      }
    },
    [scopeBrand],
  )

  const closeEvent = useCallback(() => setEventDetail(null), [])

  const strategyEmpty = panelFailed(bigIdea) && panelFailed(rightNow)
  const brandLabel = scopeBrand || 'brand'

  const yearControl = (
    <label className="flex items-center gap-2 text-sm text-tx2">
      Year
      <select
        value={yearParam}
        onChange={(e) => {
          const p = new URLSearchParams(params)
          p.set('year', e.target.value)
          setParams(p, { replace: true })
        }}
        className="rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx"
      >
        {[2026, 2027].map((y) => (
          <option key={y} value={String(y)}>
            {y}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <div className="space-y-6">
      <PageIntro icon={Map} badge="Planning" here="/calendar/lanes" title="Strategic Calendar">
        Events and commercial pushes drive the calendar. Month grid below is for daily ops.
      </PageIntro>

      <div className="flex flex-wrap items-center gap-3">
        {yearControl}
        <ClassicLink href="/?page=planning" label="planning" />
      </div>

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />

      {loading ? <p className="text-sm text-tx3">Loading planning…</p> : null}

      {tab === 'strategy' ? (
        <div className="space-y-4">
          {!scopeBrand ? (
            <p className="text-sm text-tx3">Pick a brand to load the strategic calendar.</p>
          ) : strategyEmpty ? (
            <p className="text-sm text-tx3">
              No strategic calendar data for {brandLabel}. Stick has the live event spine; other
              brands show empty states until spine files land.
            </p>
          ) : null}
          <PlanningHero brand={scopeBrand} bigIdea={bigIdea} />
          <RightNowStrip brand={brandLabel} rightNow={rightNow} onOpenEvent={openEvent} />
          {eventDetail ? (
            <div className="glass rounded-2xl border border-white/10 p-2">
              <EventDetail data={eventDetail} onClose={closeEvent} />
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'timeline' ? (
        <EventTimelinePanel
          brand={brandLabel}
          year={yearParam}
          timeline={timeline}
          eventDetail={eventDetail}
          onOpenEvent={openEvent}
          onCloseEvent={closeEvent}
        />
      ) : null}

      {tab === 'month' ? (
        <LaneMonthPanel
          brand={brandLabel}
          monthParam={monthParam}
          monthView={monthView}
          onMonthChange={setMonthParam}
        />
      ) : null}

      {tab === 'parked' ? (
        <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
          <h2 className="font-display text-lg font-semibold">Parked posts month</h2>
          <p className="text-sm text-tx2">
            The signed-off parked-posts calendar stays on the main Calendar route (P2). Open it
            there to move, park, and review scheduled pieces.
          </p>
          <Tip text="Open the Heroes parked-posts month grid (P2).">
            <Link
              to="/calendar"
              className="inline-flex rounded-full border border-yel/40 bg-yel/10 px-4 py-2 text-sm font-semibold text-yel hover:border-yel"
            >
              Open /app/calendar
            </Link>
          </Tip>
        </section>
      ) : null}
    </div>
  )
}
