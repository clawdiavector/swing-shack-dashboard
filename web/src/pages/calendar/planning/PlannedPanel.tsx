import { useEffect, useState } from 'react'
import { AlertTriangle, Calendar, ChevronRight, CircleDot, Clock } from 'lucide-react'

type PlannedItem = {
  event_id?: string
  event_name?: string
  brand_id?: string
  tier?: string
  public_peak?: string
  start?: string
  end?: string
  stage?: string
  days_to_peak?: number
  recommended_runway_weeks?: number
  planning_state?: string
  north_star_statement?: string | null
  operating_goal_match?: Array<{ id?: string; label?: string; metric?: string }>
  always_on_lane_match?: Array<{ key?: string; lane?: string; tagline?: string }>
  opportunity?: string
  evidence_source?: string | null
  phase_count?: number
  phases_suggested?: number
  phases_verified?: number
}

type PlannedResponse = {
  ok?: boolean
  brand_id?: string
  today?: string
  window_start?: string
  window_end?: string
  today_integration?: {
    briefs_due_this_week?: number
    apins_needing_creative?: number
    events_needing_planning?: number
    overdue_count?: number
    approved_count?: number
  }
  stages?: Record<string, PlannedItem[]>
  counts?: Record<string, number>
  north_star?: string | null
  operating_goals?: Array<{ id?: string; label?: string; metric?: string }>
  operating_areas?: Array<{ key?: string; lane?: string; tagline?: string }>
  big_brand_idea?: { name?: string; belief?: string }
}

const STAGE_LABELS: Record<string, { label: string; tone: string }> = {
  OVERDUE: { label: 'Overdue', tone: 'text-red-400 border-red-400/40 bg-red-500/15' },
  NEEDS_BRIEF: { label: 'Needs Brief', tone: 'text-yel border-yel/40 bg-yel/15' },
  BRIEF_READY: { label: 'Brief Ready', tone: 'text-yel border-yel/40 bg-yel/15' },
  NEEDS_CREATE: { label: 'Needs Create', tone: 'text-purple-400 border-purple-400/40 bg-purple-500/15' },
  IN_CREATE: { label: 'In Create', tone: 'text-purple-400 border-purple-400/40 bg-purple-500/15' },
  NEEDS_REVIEW: { label: 'Needs Review', tone: 'text-orange-400 border-orange-400/40 bg-orange-500/15' },
  APPROVED: { label: 'Approved', tone: 'text-emerald-400 border-emerald-400/40 bg-emerald-500/15' },
  SCHEDULED_READY_FOR_PUBLISH: { label: 'Ready for publish', tone: 'text-emerald-400 border-emerald-400/40 bg-emerald-500/15' },
}

function tierTone(t?: string): { bg: string; fg: string } {
  if (t === 'A-PIN') return { bg: 'bg-[#f0a030]/15', fg: 'text-[#f0a030]' }
  if (t === 'B-PIN') return { bg: 'bg-[#14b8a6]/15', fg: 'text-[#14b8a6]' }
  if (t === 'C-PIN') return { bg: 'bg-tx3/15', fg: 'text-tx3' }
  return { bg: 'bg-bg/80', fg: 'text-tx3' }
}

function signedDays(n?: number): string {
  if (n == null) return '—'
  if (n === 0) return 'today'
  return n > 0 ? `in ${n} days` : `${Math.abs(n)} days ago`
}

/**
 * Calendar V2.2 — Slice 5: Planned view (default TODAY → next 90 days).
 *
 * Answers: "What have we actually committed to? What needs attention next?"
 *
 * Consumes the existing Campaign OS calendar state via
 * GET /api/planning/<brand>/planned — no second calendar engine.
 *
 * Sort priority within each stage (enforced by backend):
 *   OVERDUE > this-week > A-PIN > B-PIN > runway desc
 */
export function PlannedPanel({
  brand,
  brandId,
}: {
  brand: string
  brandId: string
}) {
  const [data, setData] = useState<PlannedResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const r = await fetch(
          `/api/planning/${encodeURIComponent(brandId)}/planned`,
          { credentials: 'include' },
        )
        const j = await r.json()
        if (!r.ok || !j.ok) {
          if (!cancelled) {
            setError(j.error || 'planned view failed')
            setData(null)
          }
        } else if (!cancelled) {
          setData(j)
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'network error')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [brandId])

  if (loading && !data) {
    return (
      <section data-testid="planned-panel" className="glass space-y-4 rounded-2xl border border-white/10 p-4">
        <p className="text-tx3">Loading planned view…</p>
      </section>
    )
  }
  if (error) {
    return (
      <section data-testid="planned-panel" className="glass space-y-4 rounded-2xl border border-white/10 p-4">
        <p className="text-red-400">Error: {error}</p>
      </section>
    )
  }
  if (!data) return null

  const ti = data.today_integration || {}
  const counts = data.counts || {}
  const stages = data.stages || {}

  return (
    <section
      data-testid="planned-panel"
      className="glass space-y-4 rounded-2xl border border-white/10 p-4"
    >
      {/* Header + today integration summary */}
      <header className="space-y-2">
        <h2 className="font-display text-lg font-semibold">
          Planned view
          <span className="ml-2 text-xs font-bold tracking-wider text-tx3 uppercase">
            ({data.today} → {data.window_end} · 90 days rolling)
          </span>
        </h2>
        <div
          data-testid="today-integration-summary"
          className="flex flex-wrap items-center gap-2 text-xs"
        >
          <span className="rounded bg-bg/60 px-2 py-1 border border-bd">
            <strong className="font-bold text-yel">{ti.events_needing_planning || 0}</strong>{' '}
            <span className="text-tx2">events need planning approval</span>
          </span>
          <span className="rounded bg-bg/60 px-2 py-1 border border-bd">
            <strong className="font-bold text-red-400">{ti.overdue_count || 0}</strong>{' '}
            <span className="text-tx2">overdue (public peak passed)</span>
          </span>
          <span className="rounded bg-bg/60 px-2 py-1 border border-bd">
            <strong className="font-bold text-emerald-400">{ti.approved_count || 0}</strong>{' '}
            <span className="text-tx2">approved (ready this week)</span>
          </span>
        </div>
        {/* North Star + goals context */}
        {data.north_star ? (
          <p className="mt-2 text-[11px] text-tx3" data-testid="planned-north-star">
            <span className="font-bold text-yel">NORTH STAR:</span>{' '}
            <span className="text-tx2">{data.north_star.split('\n')[0]}</span>
          </p>
        ) : null}
        {data.operating_goals && data.operating_goals.length > 0 ? (
          <div className="mt-1 flex flex-wrap gap-2">
            {data.operating_goals.map((g) => (
              <span
                key={g.id}
                data-testid={`operating-goal-${g.id}`}
                className="rounded bg-bg/40 border border-bd px-2 py-0.5 text-[10px] text-tx2"
              >
                <span className="font-bold text-purple-400">{g.label}:</span> {g.metric}
              </span>
            ))}
          </div>
        ) : null}
      </header>

      {/* Stages — slices 3 (Brief) → 7 (publish) plus OVERDUE bucket on top */}
      <div className="space-y-4 pt-2">
        {(['OVERDUE', 'NEEDS_BRIEF', 'BRIEF_READY', 'NEEDS_CREATE', 'IN_CREATE', 'NEEDS_REVIEW', 'APPROVED', 'SCHEDULED_READY_FOR_PUBLISH'] as const).map((stage) => {
          const items = stages[stage] || []
          const meta = STAGE_LABELS[stage] || { label: stage, tone: '' }
          if (items.length === 0) return null
          return (
            <div key={stage} data-testid={`planned-stage-${stage}`} className="space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-bold tracking-wider uppercase ${meta.tone}`}
                >
                  {stage === 'OVERDUE' ? (
                    <AlertTriangle className="h-3 w-3" />
                  ) : stage === 'NEEDS_BRIEF' || stage === 'BRIEF_READY' ? (
                    <CircleDot className="h-3 w-3" />
                  ) : (
                    <Clock className="h-3 w-3" />
                  )}
                  {meta.label}
                </span>
                <span className="text-[10px] text-tx3">{items.length} item(s)</span>
              </div>
              <ul className="space-y-1">
                {items.map((it) => {
                  const tier = tierTone(it.tier)
                  return (
                    <li
                      key={`${stage}-${it.event_id}`}
                      data-testid="planned-item"
                      data-stage={stage}
                      className="rounded-lg border border-bd bg-bg2/60 px-3 py-2 text-xs"
                    >
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="font-mono text-[11px] font-bold text-tx">
                          {it.public_peak || it.start || '—'}
                        </span>
                        <span className="font-bold text-sm text-tx flex-1">{it.event_name}</span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider uppercase ${tier.bg} ${tier.fg}`}
                        >
                          {it.tier || '—'}
                        </span>
                        <span className="text-[10px] text-tx3">{signedDays(it.days_to_peak)}</span>
                        <ChevronRight className="h-3 w-3 text-tx3" />
                      </div>
                      {/* Goal/lane matches per Slice 5 directive — surfaces
                          genuinely relevant goals only; nothing forced. */}
                      {it.operating_goal_match && it.operating_goal_match.length > 0 ? (
                        <div className="mt-1 flex flex-wrap items-center gap-1">
                          <span className="text-[9px] font-bold tracking-wider text-purple-400 uppercase">
                            supports:
                          </span>
                          {it.operating_goal_match.map((g) => (
                            <span
                              key={g.id}
                              data-testid="planned-item-goal"
                              className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-purple-400 uppercase"
                              title={g.metric || ''}
                            >
                              {g.label}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {it.always_on_lane_match && it.always_on_lane_match.length > 0 ? (
                        <div className="mt-0.5 flex flex-wrap items-center gap-1">
                          <span className="text-[9px] font-bold tracking-wider text-teal-400 uppercase">
                            lane:
                          </span>
                          {it.always_on_lane_match.map((l) => (
                            <span
                              key={l.key}
                              className="rounded bg-teal-500/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-teal-400 uppercase"
                            >
                              {l.key}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {/* Phase verification summary */}
                      {typeof it.phase_count === 'number' && it.phase_count > 0 ? (
                        <p className="mt-1 text-[10px] text-tx3">
                          <Calendar className="inline h-3 w-3" />{' '}
                          {it.phases_verified}/{it.phase_count} phases verified ·{' '}
                          {it.phases_suggested} suggested
                        </p>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>

      {/* Empty state when nothing actionable */}
      {Object.values(counts).every((c) => !c) ? (
        <div className="rounded-lg border border-dashed border-bd bg-bg/40 p-6 text-center text-sm text-tx3">
          No work in the next 90 days for {brand}. Candidates (in the Timeline tab) become actionable once they're added to the spine.
        </div>
      ) : null}
    </section>
  )
}
