import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'

type Candidate = {
  id?: string
  name?: string
  category?: string
  start?: string
  end?: string
  public_peak?: string
  geography?: string
  source?: string
  source_date?: string
  relevance_to_swing_shack?: string
  opportunity?: string
  suggested_tier?: string
  confidence?: 'high' | 'medium' | 'low' | string
  recommended_lead_time_weeks?: number
  why_it_matters?: string
  added_to_spine?: boolean
  spine_event_id?: string
  verify_before_spine?: boolean
  verification_status?: string
}

// Calendar V2.1 — research_leads[] are a separate tier from candidates[].
// They are NOT dated and CANNOT be added to the spine. Operators must verify
// the date with the source/contact before graduating them to a candidate.
type ResearchLead = {
  id?: string
  name?: string
  category?: string
  geography?: string
  inferred_pattern?: string
  verification_action_needed?: string
  relevance_to_swing_shack?: string
  opportunity_if_promoted?: string
  suggested_tier_if_promoted?: string
  recommended_lead_time_weeks?: number
  why_in_research?: string
  confidence?: string
}

function confidenceTone(c?: string): { bg: string; fg: string; label: string } {
  if (c === 'high') return { bg: 'bg-emerald-500/15', fg: 'text-emerald-400', label: 'HIGH CONFIDENCE' }
  if (c === 'medium') return { bg: 'bg-yel/15', fg: 'text-yel', label: 'MEDIUM' }
  if (c === 'low') return { bg: 'bg-tx3/15', fg: 'text-tx3', label: 'LOW · VERIFY' }
  return { bg: 'bg-bg/80', fg: 'text-tx3', label: (c || '—').toUpperCase() }
}

function tierTone(t?: string): { bg: string; fg: string } {
  if (t === 'A-PIN') return { bg: 'bg-[#f0a030]/15', fg: 'text-[#f0a030]' }
  if (t === 'B-PIN') return { bg: 'bg-[#14b8a6]/15', fg: 'text-[#14b8a6]' }
  if (t === 'C-PIN') return { bg: 'bg-tx3/15', fg: 'text-tx3' }
  return { bg: 'bg-bg/80', fg: 'text-tx3' }
}

/**
 * Rolling intelligence candidates panel — Slice 6.
 *
 * Sits beneath the spine on the Timeline tab. NOT on the approved Strategic
 * Calendar — these are evidence-backed opportunities that Christelle
 * (or any human operator) must approve before they enter the spine.
 *
 * Three confidence buckets render visually distinct. Click a candidate to
 * expand its full evidence record (source URL, geography, relevance, why).
 */
export function PlanningCandidatesPanel({
  brand,
  candidates,
  candidateCount,
  confidenceBreakdown,
  researchLeads,
  researchLeadCount,
  horizon,
}: {
  brand: string
  candidates: Candidate[]
  candidateCount: number
  confidenceBreakdown: Record<string, number>
  researchLeads: ResearchLead[]
  researchLeadCount: number
  horizon: { start: string; end: string }
}) {
  const [filter, setFilter] = useState<'all' | 'high' | 'medium' | 'low'>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const sorted = useMemo(() => {
    return [...candidates].sort((a, b) => {
      const aKey = a.public_peak || a.start || ''
      const bKey = b.public_peak || b.start || ''
      return aKey.localeCompare(bKey)
    })
  }, [candidates])

  const filtered = filter === 'all' ? sorted : sorted.filter((c) => c.confidence === filter)

  const counts = {
    high: confidenceBreakdown.high || 0,
    medium: confidenceBreakdown.medium || 0,
    low: confidenceBreakdown.low || 0,
  }

  return (
    <section
      data-testid="candidates-panel"
      className="glass space-y-4 rounded-2xl border border-white/10 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">
            Intelligence · candidates
            <span className="ml-2 text-xs font-bold tracking-wider text-tx3 uppercase">
              (rolling {horizon.start} → {horizon.end})
            </span>
          </h2>
          <p className="mt-1 text-xs text-tx3">
            {candidateCount} candidates · {counts.high} high · {counts.medium} medium · {counts.low} low.
            <span className="ml-1 text-[10px] tracking-wider text-purple-400 uppercase">
              Not on the approved spine — Christelle decides what enters.
            </span>
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-bg1 p-1">
          {(['all', 'high', 'medium', 'low'] as const).map((f) => {
            const active = filter === f
            const count =
              f === 'all' ? candidateCount : f === 'high' ? counts.high : f === 'medium' ? counts.medium : counts.low
            return (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                data-testid={`candidates-filter-${f}`}
                className={`rounded px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase ${
                  active
                    ? 'bg-yel text-bg'
                    : 'bg-bg2 text-tx2 hover:border-yel/60'
                }`}
              >
                {f} {count > 0 ? `(${count})` : ''}
              </button>
            )
          })}
        </div>
      </div>

      <ul className="space-y-2">
        {filtered.map((c) => {
          const conf = confidenceTone(c.confidence)
          const tier = tierTone(c.suggested_tier)
          const expanded = expandedId === c.id
          return (
            <li
              key={c.id}
              data-testid="candidate-row"
              data-candidate-id={c.id}
              data-confidence={c.confidence}
              className="rounded-lg border border-bd bg-bg2/60"
            >
              <button
                type="button"
                onClick={() => setExpandedId(expanded ? null : c.id || null)}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
              >
                <div className="min-w-[6.5rem] text-right">
                  <p className="font-mono text-xs font-bold">{c.public_peak || c.start || '—'}</p>
                  <p className="text-[10px] text-tx3">{c.category?.replace(/-/g, ' ') || ''}</p>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold">{c.name}</p>
                  <p className="truncate text-[11px] text-tx3">{c.geography}</p>
                </div>
                <div className="hidden items-center gap-1.5 sm:flex">
                  {c.added_to_spine ? (
                    <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-emerald-400 uppercase">
                      ON SPINE
                    </span>
                  ) : null}
                  {c.verify_before_spine ? (
                    <span className="rounded bg-tx3/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-tx3 uppercase">
                      VERIFY
                    </span>
                  ) : null}
                  <span
                    className={`rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider uppercase ${tier.bg} ${tier.fg}`}
                  >
                    {c.suggested_tier || '—'}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider uppercase ${conf.bg} ${conf.fg}`}
                    data-testid="candidate-confidence"
                  >
                    {conf.label}
                  </span>
                </div>
                <div className="text-tx3">
                  {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </div>
              </button>

              {expanded ? (
                <div className="space-y-2.5 border-t border-bd px-4 py-3 text-xs">
                  <div className="grid gap-2 sm:grid-cols-2">
                    {c.relevance_to_swing_shack ? (
                      <div className="rounded-md bg-bg/60 p-2.5">
                        <p className="mb-1 text-[9px] font-bold tracking-widest text-yel uppercase">
                          Relevance to {brand}
                        </p>
                        <p className="text-tx2">{c.relevance_to_swing_shack}</p>
                      </div>
                    ) : null}
                    {c.opportunity ? (
                      <div className="rounded-md bg-bg/60 p-2.5">
                        <p className="mb-1 text-[9px] font-bold tracking-widest text-purple-400 uppercase">
                          Opportunity / commercial angle
                        </p>
                        <p className="text-tx2">{c.opportunity}</p>
                      </div>
                    ) : null}
                    {c.why_it_matters ? (
                      <div className="rounded-md bg-bg/60 p-2.5 sm:col-span-2">
                        <p className="mb-1 text-[9px] font-bold tracking-widest text-tx3 uppercase">
                          Why it matters
                        </p>
                        <p className="text-tx2">{c.why_it_matters}</p>
                      </div>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-bd pt-2 text-[10px] text-tx3">
                    {c.recommended_lead_time_weeks != null ? (
                      <span>
                        Lead time: <strong>{c.recommended_lead_time_weeks}w</strong>
                      </span>
                    ) : null}
                    {c.source_date ? (
                      <span>Source date: {c.source_date}</span>
                    ) : null}
                    {c.source ? (
                      <a
                        href={c.source}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 text-yel hover:underline"
                      >
                        Source <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </li>
          )
        })}
        {filtered.length === 0 ? (
          <li className="rounded-lg border border-bd bg-bg2/60 px-3 py-6 text-center text-sm text-tx3">
            No candidates match this filter.
          </li>
        ) : null}
      </ul>

      {/* Calendar V2.1 — Research leads. NOT dated. Cannot be promoted to the spine
          until the operator verifies the date with the listed source/contact. */}
      {researchLeadCount > 0 ? (
        <div className="border-t border-bd pt-3" data-testid="research-leads-section">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[10px] font-bold tracking-widest text-tx3 uppercase">
                Needs Verification · Research leads
              </p>
              <p className="mt-0.5 text-[10px] text-tx3">
                {researchLeadCount} leads · no confirmed dates ·{' '}
                <span className="text-tx2">Christelle: confirm date with the source before promoting.</span>
              </p>
            </div>
            <span className="rounded bg-tx3/15 px-2 py-0.5 text-[10px] font-bold tracking-wider text-tx3 uppercase">
              research only
            </span>
          </div>
          <ul className="space-y-1.5">
            {researchLeads.map((rl) => (
              <li
                key={rl.id}
                data-testid="research-lead-row"
                className="rounded-md border border-dashed border-bd bg-bg2/30 p-2.5"
              >
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-sm font-bold text-tx">{rl.name}</span>
                  <span className="rounded bg-tx3/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-tx3 uppercase">
                    {rl.category?.replace(/-/g, ' ') || '—'}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-tx2">
                  <span className="font-bold">Why:</span> {rl.relevance_to_swing_shack}
                </p>
                <p className="mt-0.5 text-[11px] text-tx3">
                  <span className="font-bold">Inferred pattern:</span> {rl.inferred_pattern}
                </p>
                <p className="mt-0.5 text-[11px] text-tx3">
                  <span className="font-bold text-yel">Verify:</span>{' '}
                  {rl.verification_action_needed}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
