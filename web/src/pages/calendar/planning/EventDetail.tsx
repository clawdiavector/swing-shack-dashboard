import { LANE_META, PIN_COLORS } from '../../../lib/planning'
import type { PlanningEventDetail } from '../../../lib/planningTypes'

const PILLAR_ORDER = ['retail', 'fitting', 'coaching'] as const
const PILLAR_COLORS: Record<string, string> = {
  retail: '#f0a030',
  fitting: '#14b8a6',
  coaching: '#f0a030',
}
const PILLAR_LABELS: Record<string, string> = {
  retail: 'RETAIL · What are we selling?',
  fitting: 'FITTING · What fitting opportunity?',
  coaching: 'COACHING · What coaching opportunity?',
}
const LANE_ORDER = ['paid', 'crm', 'campaign', 'search', 'workshop', 'apparel', 'human']

// Visual chip for planning_state — distinct from "0 phases" so the operator
// never sees a meaningless count.
function planningStateLabel(state: string | null | undefined): string {
  if (state === 'not_planned') return 'NOT PLANNED'
  if (state === 'in_flight') return 'IN FLIGHT'
  if (state === 'suggested_only') return 'SUGGESTED'
  if (state === 'completed') return 'COMPLETED'
  return '—'
}

function planningStateTone(state: string | null | undefined): {
  bg: string
  fg: string
  border: string
} {
  if (state === 'not_planned') {
    return { bg: 'bg-tx3/15', fg: 'text-tx3', border: 'border-tx3/40' }
  }
  if (state === 'in_flight') {
    return { bg: 'bg-yel/15', fg: 'text-yel', border: 'border-yel/50' }
  }
  if (state === 'suggested_only') {
    return { bg: 'bg-purple-500/15', fg: 'text-purple-400', border: 'border-purple-500/40' }
  }
  if (state === 'completed') {
    return { bg: 'bg-[#14b8a6]/15', fg: 'text-[#14b8a6]', border: 'border-[#14b8a6]/40' }
  }
  return { bg: 'bg-bg/80', fg: 'text-tx3', border: 'border-bd' }
}

export function EventDetail({
  data,
  onClose,
}: {
  data: PlanningEventDetail | null
  onClose: () => void
}) {
  if (!data?.event) return null
  const ev = data.event
  const c = PIN_COLORS[ev.tier || ''] || { fg: 'var(--color-tx)', bar: 'var(--color-tx)' }
  const pillars = ev.pillars || {}
  const lanes = ev.lanes || {}
  const phases = ev.phases || []
  const verifiedCount = phases.filter((p) => p.verified).length
  const suggestedCount = phases.length - verifiedCount
  const allSuggested = phases.length > 0 && verifiedCount === 0
  const ps = ev.planning_state
  const psLabel = planningStateLabel(ps)
  const psTone = planningStateTone(ps)

  return (
    <div className="mt-4 space-y-4 rounded-xl border border-bd bg-bg2/90 p-4 md:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded-full border px-2.5 py-0.5 text-[10px] font-bold tracking-wider uppercase"
              style={{
                background: `${c.bar}22`,
                color: c.fg,
                borderColor: `${c.bar}55`,
              }}
            >
              {ev.tier}
            </span>
            {ev.shopping_moment ? (
              <span className="rounded-full border border-purple-500/40 bg-purple-500/15 px-2 py-0.5 text-[10px] font-bold text-purple-400 uppercase">
                Shopping moment
              </span>
            ) : null}
            {ev.category ? (
              <span className="text-[10px] tracking-wider text-tx3 uppercase">{ev.category}</span>
            ) : null}
            {/* Planning state chip — replaces the meaningless "0 phases" count */}
            <span
              data-testid="event-planning-state"
              className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold tracking-wider uppercase ${psTone.bg} ${psTone.fg} ${psTone.border}`}
            >
              {psLabel}
            </span>
          </div>
          <h3 className="font-display text-2xl font-extrabold tracking-tight">{ev.name}</h3>
          {ev.commercial_push ? (
            <p className="text-sm leading-relaxed text-tx2">{ev.commercial_push}</p>
          ) : null}
        </div>
        <button
          type="button"
          className="text-2xl leading-none text-tx2 hover:text-tx"
          aria-label="Close event detail"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      {/* Key dates — verified event facts (public_peak, campaign window, planning_start) */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-bg/80 p-3">
          <p className="text-[9px] font-bold tracking-widest text-tx3 uppercase">
            Public peak
            <span className="ml-1 rounded bg-emerald-500/15 px-1 text-[8px] font-bold text-emerald-400">
              VERIFIED
            </span>
          </p>
          <p className="mt-1 text-yel font-bold">{ev.public_peak || '—'}</p>
        </div>
        <div className="rounded-lg bg-bg/80 p-3">
          <p className="text-[9px] font-bold tracking-widest text-tx3 uppercase">
            Campaign window
            <span className="ml-1 rounded bg-emerald-500/15 px-1 text-[8px] font-bold text-emerald-400">
              VERIFIED
            </span>
          </p>
          <p className="mt-1 text-sm">
            {ev.start || '—'} → {ev.end || '—'}
          </p>
        </div>
        <div className="rounded-lg bg-bg/80 p-3">
          <p className="text-[9px] font-bold tracking-widest text-tx3 uppercase">
            Planning start
            {ev.planning_start ? (
              <span className="ml-1 rounded bg-emerald-500/15 px-1 text-[8px] font-bold text-emerald-400">
                VERIFIED
              </span>
            ) : (
              <span className="ml-1 rounded bg-purple-500/15 px-1 text-[8px] font-bold text-purple-400">
                SUGGESTED
              </span>
            )}
          </p>
          <p className="mt-1 text-sm">{ev.planning_start || '—'}</p>
        </div>
        <div className="rounded-lg bg-bg/80 p-3">
          <p className="text-[9px] font-bold tracking-widest text-tx3 uppercase">Runway</p>
          <p className="mt-1 text-sm">
            {ps === 'not_planned' ? (
              <span className="font-bold text-tx3">NOT PLANNED</span>
            ) : phases.length > 0 ? (
              <>
                <span className="font-bold">{phases.length} phases</span>
                {allSuggested ? (
                  <span className="ml-1 text-[10px] tracking-wider text-purple-400 uppercase">
                    · suggested
                  </span>
                ) : suggestedCount > 0 ? (
                  <span className="ml-1 text-[10px] tracking-wider text-purple-400 uppercase">
                    · {verifiedCount} verified · {suggestedCount} suggested
                  </span>
                ) : null}
              </>
            ) : (
              '—'
            )}
          </p>
        </div>
      </div>

      {/* Runway strip — visual PLAN ── BRIEF ── CREATE ── REVIEW ── LIVE ── ★ PEAK */}
      {phases.length > 0 ? <RunwayStrip phases={phases} tierColor={c.fg} /> : null}

      {PILLAR_ORDER.some((p) => pillars[p]) ? (
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
            Core pillars
          </p>
          <div className="space-y-2">
            {PILLAR_ORDER.map((p) => {
              const v = pillars[p]
              if (!v) return null
              return (
                <div
                  key={p}
                  className="rounded-lg border-l-[3px] bg-bg/80 px-4 py-3"
                  style={{ borderColor: PILLAR_COLORS[p] }}
                >
                  <p
                    className="text-[11px] font-bold tracking-wide uppercase"
                    style={{ color: PILLAR_COLORS[p] }}
                  >
                    {PILLAR_LABELS[p]}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed">{v}</p>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {LANE_ORDER.some((l) => lanes[l]) ? (
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
            Supporting lanes
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {LANE_ORDER.map((lane) => {
              const v = lanes[lane]
              if (!v) return null
              const meta = LANE_META[lane] || { color: 'var(--color-tx3)', label: lane }
              return (
                <div key={lane} className="rounded-lg border border-bd bg-bg/80 p-3">
                  <p
                    className="text-[10px] font-bold tracking-wide uppercase"
                    style={{ color: meta.color }}
                  >
                    {meta.label}
                  </p>
                  <p className="mt-1 text-xs leading-snug">{v}</p>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {/* Phases list — chronological. Verified vs Suggested clearly labelled. */}
      {phases.length > 0 ? (
        <div>
          <div className="mb-2 flex items-center gap-3">
            <p className="text-[10px] font-bold tracking-widest text-tx3 uppercase">
              Runway phases
            </p>
            {verifiedCount > 0 ? (
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-emerald-400 uppercase">
                VERIFIED DATE
              </span>
            ) : null}
            {suggestedCount > 0 ? (
              <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-purple-400 uppercase">
                SUGGESTED PLANNING DATE
              </span>
            ) : null}
          </div>
          <div className="space-y-1">
            {phases.map((ph, i) => {
              const isPeak = ph.weeks_before_peak === 0
              const isPre = (ph.weeks_before_peak ?? 0) > 0
              const isVerified = !!ph.verified
              return (
                <div
                  key={`${ph.label}-${i}`}
                  className={`flex items-center gap-3 rounded-lg border-l-[3px] px-3 py-2 ${
                    isVerified ? 'bg-bg/80' : 'bg-purple-500/8'
                  }`}
                  style={{
                    borderColor: isPeak
                      ? c.fg
                      : isPre
                        ? isVerified
                          ? 'var(--color-tx3)'
                          : 'rgba(168,85,247,0.5)'
                        : 'rgba(20,184,166,0.5)',
                  }}
                  data-testid={`phase-${i}`}
                  data-verified={isVerified ? 'true' : 'false'}
                >
                  <span
                    className="min-w-[1.5rem] text-sm font-bold"
                    style={{ color: isPeak ? c.fg : 'var(--color-tx3)' }}
                  >
                    {i + 1}.
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold">
                      {ph.label}
                      {isPeak ? ' ⭐' : ''}
                      {!isVerified ? (
                        <span className="ml-2 rounded bg-purple-500/15 px-1 py-0.5 text-[9px] font-bold tracking-wider text-purple-400 uppercase">
                          SUGGESTED
                        </span>
                      ) : null}
                    </p>
                    {ph.task ? <p className="text-[11px] text-tx3">{ph.task}</p> : null}
                  </div>
                  <div className="text-right text-[10px] text-tx3">
                    <div>{ph.start}</div>
                    {ph.weeks_before_peak != null ? (
                      <div>
                        {ph.weeks_before_peak >= 0
                          ? `${ph.weeks_before_peak}w before`
                          : `${Math.abs(ph.weeks_before_peak)}w after`}
                      </div>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {ev.deadlines?.length ? (
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-yel uppercase">
            Decision deadlines
          </p>
          <div className="space-y-1">
            {ev.deadlines.map((d) => (
              <div
                key={`${d.label}-${d.due}`}
                className="flex justify-between rounded border-l-2 border-yel bg-yel/10 px-3 py-2"
              >
                <span className="text-xs">{d.label}</span>
                <span className="text-xs font-bold text-yel">{d.due}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

/**
 * Visual runway strip — PLAN ── BRIEF ── CREATE ── REVIEW ── LIVE ── ★ PEAK.
 * Each cell colored verified (solid tier colour) or suggested (dashed purple).
 * Pre-peak phases left of peak; post-peak right of peak.
 */
function RunwayStrip({
  phases,
  tierColor,
}: {
  phases: NonNullable<PlanningEventDetail['event']>['phases']
  tierColor: string
}) {
  if (!phases || phases.length === 0) return null
  // Identify the peak phase index (weeks_before_peak === 0) — split pre/post.
  const peakIdx = phases.findIndex((p) => p.weeks_before_peak === 0)
  const peakPh = peakIdx >= 0 ? phases[peakIdx] : phases[Math.floor(phases.length / 2)]
  const prePhases = phases.filter((p) => (p.weeks_before_peak ?? 0) > 0)
  const postPhases = phases.filter((p) => (p.weeks_before_peak ?? 0) < 0)

  return (
    <div>
      <div className="mb-2 flex items-center gap-3">
        <p className="text-[10px] font-bold tracking-widest text-tx3 uppercase">Runway</p>
        <span className="flex items-center gap-1.5 text-[10px] text-tx3">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ background: tierColor }}
          />
          Verified phase
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-tx3">
          <span
            className="inline-block h-2 w-3 rounded-sm border border-dashed border-purple-500/70 bg-purple-500/15"
          />
          Suggested phase
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-bd bg-bg/80 p-3">
        <div className="flex min-w-fit items-center gap-1">
          {prePhases.map((ph, i) => (
            <RunwayCell
              key={`pre-${i}`}
              label={ph.label || ''}
              verified={!!ph.verified}
              tierColor={tierColor}
              side="pre"
              isLast={i === prePhases.length - 1 && postPhases.length === 0}
            />
          ))}
          {peakPh ? (
            <RunwayCell
              key="peak"
              label="★ PEAK"
              verified={!!peakPh.verified}
              tierColor={tierColor}
              side="peak"
              isLast={postPhases.length === 0}
            />
          ) : null}
          {postPhases.map((ph, i) => (
            <RunwayCell
              key={`post-${i}`}
              label={ph.label || ''}
              verified={!!ph.verified}
              tierColor={tierColor}
              side="post"
              isLast={i === postPhases.length - 1}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function RunwayCell({
  label,
  verified,
  tierColor,
  side,
  isLast,
}: {
  label: string
  verified: boolean
  tierColor: string
  side: 'pre' | 'peak' | 'post'
  isLast: boolean
}) {
  const isPeak = side === 'peak'
  const baseCls = isPeak
    ? 'min-w-[5rem] px-3 py-2 text-center text-[10px] font-bold tracking-wider'
    : 'min-w-[4rem] px-2 py-2 text-center text-[10px] font-bold tracking-wider'
  const style: React.CSSProperties = verified
    ? isPeak
      ? { background: tierColor, color: '#0d0d0d' }
      : { background: `${tierColor}30`, color: tierColor }
    : {
        background: 'transparent',
        color: 'rgba(168,85,247,0.85)',
        border: '1px dashed rgba(168,85,247,0.55)',
      }
  return (
    <>
      <div className={baseCls} style={style} data-testid={`runway-cell-${side}-${label}`}>
        {label}
      </div>
      {!isLast ? (
        <div
          className="h-px w-3 shrink-0"
          style={{ background: verified ? tierColor : 'rgba(168,85,247,0.4)' }}
        />
      ) : null}
    </>
  )
}
