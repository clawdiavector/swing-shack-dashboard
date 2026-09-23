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

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(
          [
            ['Public peak', ev.public_peak || '—', 'text-yel font-bold'],
            ['Campaign window', `${ev.start || '—'} → ${ev.end || '—'}`, 'text-sm'],
            ['Planning start', ev.planning_start || '—', 'text-sm'],
            ['Runway', `${ev.phases?.length || 0} phases`, 'text-sm'],
          ] as const
        ).map(([label, value, cls]) => (
          <div key={label} className="rounded-lg bg-bg/80 p-3">
            <p className="text-[9px] font-bold tracking-widest text-tx3 uppercase">{label}</p>
            <p className={`mt-1 ${cls}`}>{value}</p>
          </div>
        ))}
      </div>

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

      {ev.phases?.length ? (
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
            Runway phases
          </p>
          <div className="space-y-1">
            {ev.phases.map((ph, i) => {
              const isPeak = ph.weeks_before_peak === 0
              const isPre = (ph.weeks_before_peak ?? 0) > 0
              return (
                <div
                  key={`${ph.label}-${i}`}
                  className="flex items-center gap-3 rounded-lg border-l-[3px] bg-bg/80 px-3 py-2"
                  style={{
                    borderColor: isPeak ? c.fg : isPre ? 'var(--color-tx3)' : 'rgba(20,184,166,0.5)',
                  }}
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
