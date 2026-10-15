import { Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import '../../fun.css'
import { FunTile } from '../../components/fun'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { PageIntro } from '../../components/chrome'
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
import { AlertBanner } from './planning/AlertBanner'
import { TriagePanel } from './planning/TriagePanel'
import { fetchTriage } from '../../lib/calendarSuggestions'
import { LaneMonthPanel } from './planning/LaneMonthPanel'
import { PlanList } from './planning/PlanList'
import { PlanningCandidatesPanel } from './planning/PlanningCandidatesPanel'
import { PlanningContextModal } from './planning/PlanningContextModal'
import { PlanningHero } from './planning/PlanningHero'
import { RightNowStrip } from './planning/RightNowStrip'
import { SearchPanel } from './planning/SearchPanel'
import { SuggestDateModal } from './planning/SuggestDateModal'
import { WaitingForYou } from './planning/WaitingForYou'

type LanesTab = 'list' | 'month'

// One calendar, three ways to look at it. The switch sits at the top of
// the page and List is the default; everything else on the page stays put
// whichever view is showing. Old ?tab=strategy links land on List.
const TAB_OPTIONS: { id: LanesTab; label: string; hint: string }[] = [
  { id: 'list', label: 'List', hint: 'Everything coming up as rows, soonest first' },
  { id: 'month', label: 'Month', hint: 'Day-by-day grid for one month' },
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
  const rawTab = params.get('tab') || 'list'
  const tab: LanesTab = VALID_TABS.has(rawTab) ? (rawTab as LanesTab) : 'list'

  const monthParam =
    params.get('month') ||
    `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`

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
  const [showTriage, setShowTriage] = useState(false)
  const [triageCount, setTriageCount] = useState<number | null>(null)
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

  // The calendar's own entries plus the dates to note, as one list for both views.
  const withDatesToNote = useMemo(
    () =>
      timeline
        ? { ...timeline, events: [...(timeline.events || []), ...(timeline.dates_to_note || [])] }
        : timeline,
    [timeline],
  )

  const openEvent = useCallback(
    async (eventId: string) => {
      if (!scopeBrand || eventId.startsWith('note:')) return
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

  // How many important dates are waiting for a yes or no, for the Sort dates button.
  useEffect(() => {
    if (!scopeBrand) return
    let cancelled = false
    void fetchTriage(scopeBrand).then((r) => {
      if (!cancelled) setTriageCount(r.ok ? (r.items || []).length : null)
    })
    return () => {
      cancelled = true
    }
  }, [scopeBrand, refreshKey])

  const strategyEmpty = panelFailed(bigIdea) && panelFailed(rightNow)
  const brandLabel = scopeBrand || 'brand'
  const soonCount = useMemo(() => {
    const pad = (n: number) => String(n).padStart(2, '0')
    const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    const from = new Date()
    const to = new Date()
    to.setDate(to.getDate() + 30)
    const a = iso(from)
    const b = iso(to)
    return (withDatesToNote?.events || []).filter((ev) => {
      const s = (ev.start || ev.public_peak || ev.planning_start || '').slice(0, 10)
      return s >= a && s <= b
    }).length
  }, [withDatesToNote])

  const openSuggestDate = (iso?: string) => {
    setSuggestDateInitial(iso)
    setShowSuggestDate(true)
  }

  return (
    <div className="space-y-6">
      <PageIntro badge="Planning" here="/calendar/lanes" title="Plan">
        What’s coming up, soonest first. Anything you’ve suggested waits at the top until you put it on the calendar.
      </PageIntro>

      {scopeBrand && timeline ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <FunTile
            label="Next 30 days"
            value={soonCount}
            hint={soonCount === 1 ? 'Thing on the calendar' : 'Things on the calendar'}
            tone="gold"
            dots={{ on: Math.min(soonCount, 7) }}
          />
          <FunTile
            label="Ideas to review"
            value={candidates ? candidates.candidate_count || 0 : '—'}
            hint="Found by research"
            tone="violet"
          />
          <FunTile label="Dates to sort" value={triageCount ?? 0} hint="Waiting for a decision" tone="blue" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span
            className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-bg1 p-1"
            role="tablist"
            aria-label="Calendar view"
          >
            {TAB_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="tab"
                aria-selected={tab === opt.id}
                title={opt.hint}
                onClick={() => setTab(opt.id)}
                data-testid={`plan-view-${opt.id}`}
                className={`fun-btn rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
                  tab === opt.id ? 'bg-yel text-bg' : 'text-tx2 hover:text-tx'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </span>
        </div>
        {scopeBrand && triageCount ? (
          <button
            type="button"
            onClick={() => setShowTriage((v) => !v)}
            data-testid="plan-triage-open"
            className="fun-btn inline-flex items-center gap-1.5 rounded-full border border-yel/40 px-4 py-2 text-sm font-semibold text-yel hover:bg-yel/10"
          >
            Sort dates · {triageCount}
          </button>
        ) : null}
        {scopeBrand ? (
          <button
            type="button"
            onClick={() => openSuggestDate()}
            data-testid="plan-new"
            className="fun-btn inline-flex items-center gap-1.5 rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg hover:bg-yel/90"
          >
            <Plus className="h-4 w-4" strokeWidth={2.5} />
            New date or campaign
          </button>
        ) : null}
      </div>

      <AlertBanner brandId={scopeBrand || ''} refreshKey={refreshKey} />

      {showTriage && scopeBrand ? (
        <TriagePanel
          brandId={scopeBrand}
          onClose={() => setShowTriage(false)}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      ) : null}

      {!scopeBrand ? <p className="text-sm text-tx3">Pick a brand to load its plan.</p> : null}

      {scopeBrand ? (
        <WaitingForYou
          brandId={scopeBrand}
          refreshKey={refreshKey}
          onApprove={approveCandidate}
          onOpenDetails={openPlanningByCandidateId}
        />
      ) : null}

      {loading ? <p className="text-sm text-tx3">Unrolling the calendar…</p> : null}

      {tab === 'list' && scopeBrand && timeline ? (
        <PlanList
          brandId={scopeBrand}
          events={withDatesToNote?.events || []}
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
          onSuggestDate={openSuggestDate}
          brandId={scopeBrand || ''}
          onChanged={() => setRefreshKey((k) => k + 1)}
        />
      ) : null}

      {/* Below the calendar, the same on every view: find a date, ideas
          from research, then the strategy the calendar serves. */}
      {scopeBrand ? (
        <div className="space-y-4">
          <SearchPanel
            brand={brandLabel}
            brandId={scopeBrand}
            onAddToMainCalendar={approveCandidate}
            onOpenPlanning={openPlanningByCandidateId}
            onOpenIntelligence={openPlanningByCandidateId}
            onOpenSuggestDateModal={() => openSuggestDate()}
            refreshKey={searchRefreshKey}
          />
          {candidates ? (
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
          {strategyEmpty ? (
            <p className="text-sm text-tx3">
              There are no planned dates for {brandLabel} yet.
            </p>
          ) : null}
          <PlanningHero brand={scopeBrand} bigIdea={bigIdea} />
          <RightNowStrip brand={brandLabel} bigIdea={bigIdea} rightNow={rightNow} onOpenEvent={openEvent} />
        </div>
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
