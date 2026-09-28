import { useEffect, useState } from 'react'
import { AlertCircle, ChevronRight, ExternalLink, FileText, Loader2, X } from 'lucide-react'

type PlanningContext = {
  event?: { name?: string; category?: string; verified_date?: string; public_peak?: string | null }
  brand?: string
  verified_dates?: { start?: string; end?: string; public_peak?: string } | null
  tier?: string | null
  recommended_tier?: string | null
  runway?: { recommended_lead_time_weeks?: number | null }
  north_star?: string | null
  operating_goal_match?: Array<{ id?: string; label?: string; metric?: string }>
  always_on_lane_match?: Array<{ key?: string; lane?: string; tagline?: string }>
  evidence?: {
    source?: string | null
    source_date?: string | null
    geography?: string | null
    verification_status?: string | null
    venue_status?: string | null
    date_status?: string | null
    opportunity?: string | null
    relevance?: string | null
    why_it_matters?: string | null
  }
  planning_state?: string
  existing_brief?: { brief_id?: string; exists?: boolean } | null
  open_planning_action?: string
}

type PlanningContextResponse = {
  ok?: boolean
  brand_id?: string
  candidate_id?: string
  is_research_lead?: boolean
  is_approved?: boolean
  event_key?: string | null
  verification_required?: boolean
  verification_action_needed?: string
  context?: PlanningContext
  error?: string
}

/**
 * Calendar V2.3 — Slice 3 visible OPEN PLANNING context.
 *
 * Renders every field the operator's OPEN PLANNING directive required:
 *   - event
 *   - brand
 *   - verified dates
 *   - public peak
 *   - tier
 *   - runway
 *   - north star
 *   - relevant operating goal(s)
 *   - relevant lane(s)
 *   - evidence (source URL + source date + venue status + opportunity + relevance)
 *   - planning_state
 *   - existing brief (V2.3 reuse)
 *
 * Does NOT create a second planning system — it surfaces the planning
 * context.OPEN EXISTING BRIEF is shown when one exists. CREATE BRIEF
 * is shown when approved but no brief yet exists. VERIFY BEFORE ADDING
 * for research_leads. The actual write side stays on the existing
 * /api/brief/v1/* endpoints.
 */
export function PlanningContextModal({
  brandId,
  candidateId,
  onClose,
}: {
  brandId: string
  candidateId: string
  onClose: () => void
}) {
  const [data, setData] = useState<PlanningContextResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const r = await fetch(
          `/api/planning/${encodeURIComponent(brandId)}/candidates/${encodeURIComponent(candidateId)}/planning-context`,
          { credentials: 'include' },
        )
        const j = await r.json()
        if (!cancelled) {
          setData(j)
          if (!r.ok) setError(j.error || 'context failed')
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'network')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [brandId, candidateId])

  return (
    <div
      data-testid="planning-context-modal"
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative max-h-[90vh] w-[min(720px,95vw)] overflow-y-auto rounded-2xl border border-white/10 bg-bg2 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          data-testid="planning-context-close"
          onClick={onClose}
          className="absolute right-3 top-3 rounded-md border border-bd p-1.5 text-tx3 hover:bg-bg"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        <header>
          <p className="text-[10px] font-bold tracking-widest text-yel uppercase">
            Open Planning
          </p>
          {loading ? (
            <p className="mt-1 text-sm text-tx3">
              <Loader2 className="inline h-3 w-3 animate-spin" /> Loading context…
            </p>
          ) : error ? (
            <p className="mt-1 text-sm text-red-400">Error: {error}</p>
          ) : data?.is_research_lead ? (
            <ResearchLeadContext data={data} />
          ) : data?.context ? (
            <h2 className="mt-1 font-display text-lg font-semibold text-tx">
              {data.context.event?.name || candidateId}
            </h2>
          ) : null}
        </header>

        {data?.context && !data.is_research_lead ? (
          <ContextBody data={data} />
        ) : null}
      </div>
    </div>
  )
}

function ResearchLeadContext({ data }: { data: PlanningContextResponse }) {
  return (
    <div className="mt-3 space-y-3">
      <div
        className="rounded-md border border-yel/40 bg-yel/15 p-3 text-sm"
        data-testid="research-lead-context"
      >
        <div className="flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 text-yel flex-shrink-0" />
          <div>
            <p className="font-bold text-yel">VERIFY BEFORE ADDING</p>
            <p className="mt-1 text-tx2">This candidate is a research lead without a verified date.</p>
            <p className="mt-1 text-[11px] text-tx3">
              <strong>Action:</strong> {data.verification_action_needed || 'Confirm the date with the source/contact first.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function ContextBody({ data }: { data: PlanningContextResponse }) {
  const c = data.context as PlanningContext
  const v = c.verified_dates || {}
  return (
    <div className="mt-4 space-y-4 text-xs">
      {/* brand + event_key + planning_state */}
      <div className="grid gap-2 sm:grid-cols-2">
        <KV label="Brand" value={c.brand || data.brand_id || '—'} />
        <KV
          label="Planning state"
          value={
            c.planning_state === 'on_spine'
              ? '✓ ON SPINE'
              : c.planning_state === 'not_yet_on_spine'
              ? 'Not yet on spine'
              : c.planning_state ?? '—'
          }
          tone={c.planning_state === 'on_spine' ? 'good' : 'neutral'}
        />
        {data.event_key ? (
          <KV label="event_key" value={data.event_key} mono />
        ) : null}
        {c.tier ? <KV label="Tier" value={c.tier} tone="tier" /> : null}
      </div>

      {/* verified dates + runway */}
      <div className="grid gap-2 sm:grid-cols-3">
        <KV label="Verified start" value={v.start || '—'} mono />
        <KV label="Verified end" value={v.end || '—'} mono />
        <KV label="Public peak" value={v.public_peak || '—'} mono />
      </div>
      {c.runway?.recommended_lead_time_weeks != null ? (
        <KV
          label="Recommended runway"
          value={`${c.runway.recommended_lead_time_weeks} weeks before peak`}
        />
      ) : null}

      {/* North Star */}
      {c.north_star ? (
        <section className="rounded-md bg-bg/40 border border-bd p-3">
          <p className="text-[9px] font-bold tracking-widest text-yel uppercase">
            North Star
          </p>
          <p className="mt-1 whitespace-pre-line text-tx2" data-testid="planning-north-star">{c.north_star}</p>
        </section>
      ) : null}

      {/* operating goals + lanes */}
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <p className="text-[9px] font-bold tracking-widest text-purple-400 uppercase">
            Relevant operating goal(s)
          </p>
          {c.operating_goal_match && c.operating_goal_match.length > 0 ? (
            <ul className="mt-1 space-y-1">
              {c.operating_goal_match.map((g) => (
                <li
                  key={g.id}
                  data-testid="planning-op-goal"
                  className="rounded bg-purple-500/15 px-2 py-1 text-[10px]"
                >
                  <strong className="text-purple-400">{g.label}:</strong>{' '}
                  <span className="text-tx2">{g.metric}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-tx3">No relevant operating goal match for this event.</p>
          )}
        </div>
        <div>
          <p className="text-[9px] font-bold tracking-widest text-teal-400 uppercase">
            Always-on lane(s)
          </p>
          {c.always_on_lane_match && c.always_on_lane_match.length > 0 ? (
            <ul className="mt-1 space-y-1">
              {c.always_on_lane_match.map((l) => (
                <li
                  key={l.key}
                  data-testid="planning-lane"
                  className="rounded bg-teal-500/15 px-2 py-1 text-[10px]"
                >
                  <strong className="text-teal-400">{l.key}</strong>{' '}
                  <span className="text-tx2">— {l.tagline}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-tx3">No lane match.</p>
          )}
        </div>
      </div>

      {/* evidence */}
      {c.evidence ? (
        <section className="rounded-md bg-bg/40 border border-bd p-3">
          <p className="text-[9px] font-bold tracking-widest text-bd uppercase">Evidence</p>
          <dl className="mt-2 grid gap-1.5 sm:grid-cols-2">
            <KV label="Geography" value={c.evidence.geography || '—'} />
            <KV
              label="Verification"
              value={c.evidence.verification_status || '—'}
              tone={c.evidence.verification_status === 'verified' ? 'good' : 'neutral'}
            />
            {c.evidence.venue_status ? <KV label="Venue" value={c.evidence.venue_status} /> : null}
            {c.evidence.date_status ? <KV label="Date" value={c.evidence.date_status} /> : null}
            <KV label="Source date" value={c.evidence.source_date || '—'} />
            {c.evidence.source ? (
              <a
                href={c.evidence.source}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 text-yel hover:underline"
              >
                Source <ExternalLink className="h-3 w-3" />
              </a>
            ) : null}
            {c.evidence.relevance ? (
              <dd className="sm:col-span-2 text-tx2">
                <strong className="font-bold">Relevance:</strong> {c.evidence.relevance}
              </dd>
            ) : null}
            {c.evidence.opportunity ? (
              <dd className="sm:col-span-2 text-tx2">
                <strong className="font-bold">Opportunity:</strong> {c.evidence.opportunity}
              </dd>
            ) : null}
            {c.evidence.why_it_matters ? (
              <dd className="sm:col-span-2 text-tx2">
                <strong className="font-bold">Why it matters:</strong> {c.evidence.why_it_matters}
              </dd>
            ) : null}
          </dl>
        </section>
      ) : null}

      {/* Existing brief reuse — the V2.3 acceptance point. */}
      <section
        className="rounded-md bg-bg/40 border border-bd p-3"
        data-testid="planning-brief-section"
      >
        <div className="flex flex-wrap items-baseline gap-2">
          <p className="text-[9px] font-bold tracking-widest text-emerald-400 uppercase">
            Existing brief
          </p>
          {c.existing_brief?.exists ? (
            <>
              <FileText className="h-3.5 w-3.5 text-emerald-400" />
              <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold tracking-wider text-emerald-400 uppercase">
                Brief exists
              </span>
              <code className="font-mono text-[11px] text-tx2">{c.existing_brief.brief_id}</code>
              <ChevronRight className="h-3.5 w-3.5 text-tx3" />
              <button
                type="button"
                data-testid="open-existing-brief-btn"
                onClick={() => {
                  const bi = c.existing_brief?.brief_id || ''
                  window.location.href = `/app/brief/${encodeURIComponent(c.brand || data.brand_id || '')}/${encodeURIComponent(bi)}`
                }}
                className="rounded border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-1 text-[10px] font-bold tracking-wider text-emerald-400 uppercase hover:bg-emerald-500/25"
              >
                OPEN EXISTING BRIEF
              </button>
            </>
          ) : c.planning_state === 'on_spine' ? (
            <>
              <span className="rounded border border-bd bg-bg/40 px-2 py-0.5 text-[10px] text-tx2">
                No brief yet
              </span>
              <ChevronRight className="h-3.5 w-3.5 text-tx3" />
              <button
                type="button"
                data-testid="create-brief-btn"
                onClick={() => {
                  // V2.3 reuse rule: do NOT auto-create. Hand off to the
                  // Brief screen which keeps a single planning system.
                  window.location.href = `/app/brief/${encodeURIComponent(c.brand || data.brand_id || '')}/new?event_key=${encodeURIComponent(data.event_key || '')}`
                }}
                className="rounded border border-yel/40 bg-yel/15 px-2.5 py-1 text-[10px] font-bold tracking-wider text-yel uppercase hover:bg-yel/25"
              >
                CREATE BRIEF
              </button>
              <span className="ml-1 text-[10px] text-tx3">
                (Loading existing /app/brief/{c.brand || data.brand_id || ''}/new workflow)
              </span>
            </>
          ) : (
            <span className="rounded border border-tx3/30 bg-tx3/10 px-2 py-0.5 text-[10px] text-tx3">
              Approve the candidate first to enable brief creation.
            </span>
          )}
        </div>
      </section>
    </div>
  )
}

function KV({
  label,
  value,
  mono,
  tone,
}: {
  label: string
  value: string
  mono?: boolean
  tone?: 'good' | 'neutral' | 'tier'
}) {
  let valueClass = 'text-tx2'
  if (tone === 'good') valueClass = 'text-emerald-400 font-bold'
  if (tone === 'tier') valueClass = 'text-[#f0a030] font-bold'
  return (
    <div>
      <dt className="text-[9px] font-bold tracking-widest text-bd uppercase">{label}</dt>
      <dd className={`mt-0.5 ${mono ? 'font-mono text-tx' : ''} ${valueClass}`}>{value}</dd>
    </div>
  )
}
