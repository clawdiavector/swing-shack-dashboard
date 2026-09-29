import { Map } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import {
  fetchPlanningBigIdea,
  fetchPlanningCandidates,
  fetchPlanningEvent,
  fetchPlanningMonth,
  fetchPlanningRightNow,
  fetchPlanningTimelineRange,
} from '../../lib/api'
import {
  getCachedPlanningEvent,
  planningEventCacheKey,
  setCachedPlanningEvent,
} from '../../lib/planning'
import { localTodayIso } from '../../lib/planning'
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
import { PlanningCandidatesPanel } from './planning/PlanningCandidatesPanel'
import { PlanningContextModal } from './planning/PlanningContextModal'
import { PlanningHero } from './planning/PlanningHero'
import { RightNowStrip } from './planning/RightNowStrip'
import { SearchPanel } from './planning/SearchPanel'
import { SuggestDateModal } from './planning/SuggestDateModal'

type LanesTab = 'strategy' | 'month'

// V2.11 — collapsed to 2 in-page tabs. The Calendar lives under the
// main Calendar nav entry in the Shell; adding more inner tabs here
// creates places to get lost (operator directive 2026-09-29).
const TAB_OPTIONS = [
  { id: 'strategy', label: 'Strategy' },
  { id: 'month', label: 'Month' },
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
  const [candidates, setCandidates] = useState<{
    candidates?: Array<Record<string, unknown>>
    candidate_count?: number
    confidence_breakdown?: Record<string, number>
    research_leads?: Array<Record<string, unknown>>
    research_lead_count?: number
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [eventDetail, setEventDetail] = useState<PlanningEventDetail | null>(null)
  // V2.10 — refresh the planning data after a successful candidate
  // approval. The previous build only re-fetched on brand / month
  // change, so approving a candidate left the timeline / month grid
  // showing the old state. Bumping refreshKey triggers a re-load.
  const [refreshKey, setRefreshKey] = useState(0)
  // V2.9 §3+§5 — refresh the search results after a Suggest Date
  // submission so the new candidate appears immediately.
  const [searchRefreshKey, setSearchRefreshKey] = useState(0)
  const [showSuggestDate, setShowSuggestDate] = useState(false)
  // V2.11 — Month-tab add-to-main-calendar shortcut. Clicking the "+"
  // on a day cell opens the SuggestDateModal pre-filled with that date.
  const [suggestDateInitial, setSuggestDateInitial] = useState<string | undefined>(undefined)
  // Reused Open Planning modal (Slice 3) — also used by SearchPanel
  const [openPlanningFor, setOpenPlanningFor] = useState<{ brandId: string; candidateId: string } | null>(null)

  // Calendar V2: rolling date-range horizon anchored on today.
  // Span = the visible 12-month window. The cross-year endpoint dedupes events
  // across multiple spine year files, which is essential because the year
  // boundary falls inside the visible window (e.g. today=28 Sep 2026, 12M → 28 Sep 2027).
  const horizon = useMemo(() => {
    const today = new Date(`${localTodayIso()}T00:00:00`)
    const startD = today
    const endD = new Date(today)
    endD.setFullYear(endD.getFullYear() + 1)
    return {
      start: startD.toISOString().slice(0, 10),
      end: endD.toISOString().slice(0, 10),
    }
  }, [])

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
      safeLoad(() => fetchPlanningTimelineRange(scopeBrand, horizon.start, horizon.end)),
      safeLoad(() => fetchPlanningCandidates(scopeBrand, { start: horizon.start, end: horizon.end })),
    ]).then(([bi, rn, mo, tl, cand]) => {
      if (gone) return
      setBigIdea(bi as PlanningBigIdeaResponse)
      setRightNow(rn as PlanningRightNow)
      setMonthView(mo as PlanningMonthView)
      setTimeline(tl as PlanningTimeline)
      setCandidates(cand as { candidates?: Array<Record<string, unknown>>; candidate_count?: number; confidence_breakdown?: Record<string, number> } | null)
      setLoading(false)
    })
    return () => {
      gone = true
    }
  }, [scopeBrand, monthParam, horizon.start, horizon.end, refreshKey])

  // V2.10 — single approval entry point used by the Candidates panel
  // AND the SearchPanel. Re-fetches the planning data so the timeline
  // and month grid update without a page reload.
  const approveCandidate = useCallback(
    async (candidateId: string) => {
      if (!scopeBrand) return { ok: false, error: 'no brand' }
      try {
        const r = await fetch(
          `/api/planning/${encodeURIComponent(scopeBrand)}/candidates/${encodeURIComponent(candidateId)}/approve`,
          { method: 'POST', credentials: 'include', headers: { 'X-Actor': 'operator' } },
        )
        const j = await r.json()
        if (r.ok && j.ok) {
          // Bump refreshKey so the timeline + month re-fetch.
          setRefreshKey((k) => k + 1)
          setSearchRefreshKey((k) => k + 1)
          return { ok: true, event_key: j.event_key, was_created: j.was_created }
        }
        return { ok: false, error: j.error, is_research_lead: j.is_research_lead }
      } catch (e: unknown) {
        return { ok: false, error: e instanceof Error ? e.message : 'network error' }
      }
    },
    [scopeBrand],
  )

  // V2.9 §3 — Search panel open-planning handler reuses the same
  // planning context modal as the candidates panel.
  const openPlanningByCandidateId = useCallback(
    (candidateId: string) => {
      if (!scopeBrand) return
      setOpenPlanningFor({ brandId: scopeBrand, candidateId })
    },
    [scopeBrand],
  )

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
          <RightNowStrip brand={brandLabel} bigIdea={bigIdea} rightNow={rightNow} onOpenEvent={openEvent} />
          {/* V2.11 — inline timeline + candidates inside Strategy so the
              Calendar surface shows approved spine + rolling intelligence
              candidates in one view. No inner-tab navigation. */}
          {scopeBrand ? (
            <SearchPanel
              brand={brandLabel}
              brandId={scopeBrand}
              onAddToMainCalendar={approveCandidate}
              onOpenPlanning={openPlanningByCandidateId}
              onOpenIntelligence={openPlanningByCandidateId}
              onOpenSuggestDateModal={() => {
                setSuggestDateInitial(undefined)
                setShowSuggestDate(true)
              }}
              refreshKey={searchRefreshKey}
            />
          ) : null}
          <EventTimelinePanel
            brand={brandLabel}
            year={yearParam}
            timeline={timeline}
            eventDetail={eventDetail}
            onOpenEvent={openEvent}
            onCloseEvent={closeEvent}
          />
          {scopeBrand && candidates ? (
            <PlanningCandidatesPanel
              brand={brandLabel}
              brandId={scopeBrand}
              candidates={candidates.candidates || []}
              candidateCount={candidates.candidate_count || 0}
              confidenceBreakdown={candidates.confidence_breakdown || {}}
              researchLeads={candidates.research_leads || []}
              researchLeadCount={candidates.research_lead_count || 0}
              horizon={horizon}
              onApproved={() => {
                setRefreshKey((k) => k + 1)
                setSearchRefreshKey((k) => k + 1)
              }}
            />
          ) : null}
          {eventDetail ? (
            <div className="glass rounded-2xl border border-white/10 p-2">
              <EventDetail data={eventDetail} onClose={closeEvent} />
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'month' ? (
        <LaneMonthPanel
          brand={brandLabel}
          monthParam={monthParam}
          monthView={monthView}
          onMonthChange={setMonthParam}
          onSuggestDate={(iso) => {
            setSuggestDateInitial(iso)
            setShowSuggestDate(true)
          }}
        />
      ) : null}
      {/* V2.9 §5 — Operator date suggestion. Submits to /api/calendar/candidates
          (the existing intake endpoint). Never auto-approves. */}
      {showSuggestDate && scopeBrand ? (
        <SuggestDateModal
          brand={brandLabel}
          brandId={scopeBrand}
          onClose={() => {
            setShowSuggestDate(false)
            setSuggestDateInitial(undefined)
          }}
          onSubmitted={(result) => {
            if (result.ok) {
              setSearchRefreshKey((k) => k + 1)
              setRefreshKey((k) => k + 1)
              setShowSuggestDate(false)
              setSuggestDateInitial(undefined)
            }
          }}
          initialDate={suggestDateInitial}
        />
      ) : null}

      {/* V2.9 §3+§7 — Open Planning modal. Reused from the candidates panel
          and the Search panel. Single source of truth for candidate
          planning context (no duplicate planning system). */}
      {openPlanningFor ? (
        <PlanningContextModal
          brandId={openPlanningFor.brandId}
          candidateId={openPlanningFor.candidateId}
          onClose={() => setOpenPlanningFor(null)}
        />
      ) : null}
    </div>
  )
}
