import { deadlineDayLabel, PIN_COLORS } from '../../../lib/planning'
import type { PlanningRightNow, PlanningTimelineEvent } from '../../../lib/planningTypes'

function ActivePinList({
  events,
  onOpenEvent,
}: {
  events?: PlanningTimelineEvent[]
  onOpenEvent: (id: string) => void
}) {
  if (!events?.length) {
    return <span className="text-tx3 italic">none right now</span>
  }
  return (
    <div className="space-y-1">
      {events.slice(0, 4).map((ev) => {
        const tier = ev.tier || ''
        const c = PIN_COLORS[tier] || { fg: 'var(--color-tx2)' }
        return (
          <div key={ev.id} className="text-xs leading-snug">
            <span className="font-bold" style={{ color: c.fg }}>
              {tier}
            </span>
            {' · '}
            <button
              type="button"
              className="border-b border-dotted text-tx hover:text-yel"
              style={{ borderColor: c.fg }}
              onClick={() => onOpenEvent(ev.id)}
            >
              {ev.name || '—'}
            </button>
          </div>
        )
      })}
    </div>
  )
}

export function RightNowStrip({
  brand,
  bigIdea,
  rightNow,
  onOpenEvent,
}: {
  brand: string
  bigIdea?: { operating_areas?: Array<{ key?: string }> } | null
  rightNow: PlanningRightNow | null
  onOpenEvent: (id: string) => void
}) {
  if (!rightNow?.ok) {
    return (
      <section className="glass rounded-2xl border border-yel/20 p-4">
        <p className="text-sm text-tx3">
          No right-now strip for {brand}. Event spine data is only loaded for Stick today.
        </p>
      </section>
    )
  }

  const rn = rightNow.right_now || {}
  const today = rightNow.today || ''

  // V2.11 — Right Now labels are brand-specific. The previous build
  // hard-coded RETAIL / FITTING / COACHING, which is correct for
  // Stick but wrong for Swing Shack (no RETAIL area) and misleading
  // for Bag Drop. Pull the labels from the canonical
  // bigIdea.operating_areas[].key list (first 3) and fall back to
  // whichever right_now keys have content. Each label gets the
  // matching right_now key by lowercased label match.
  const areaKeys = (bigIdea?.operating_areas || []).map((a) => (a.key || '').toUpperCase())
  const fallbackLabels = ['RETAIL', 'FITTING', 'COACHING']
  const labels = (areaKeys.length > 0 ? areaKeys : fallbackLabels).slice(0, 3)
  const colorFor = (k: string): string => {
    const u = (k || '').toUpperCase()
    if (u === 'FITTING' || u === 'CONDITION' || u === 'MEASUREMENT') return '#14b8a6'
    return '#f0a030'
  }
  const cardFor = (label: string): { color: string; text: string } => {
    const color = colorFor(label)
    // Prefer exact lowercased match (rightNow.retail). Fall back to
    // common synonyms (e.g. 'lessons' for the right_now.retail
    // slot). Then the generic copy as a last resort.
    const key = label.toLowerCase()
    const text = rn[key]
      || (label === 'FITTING' ? (rn.fitting || null) : null)
      || (label === 'COACHING' ? (rn.coaching || null) : null)
      || (label === 'ON-COURSE' ? (rn.on_course || null) : null)
      || (label === 'HUMAN' ? (rn.human || null) : null)
      || (label === 'MEASUREMENT' ? (rn.measurement || null) : null)
      || null
    return { color, text: text || '—' }
  }

  return (
    <section className="glass space-y-4 rounded-2xl border border-yel/20 bg-gradient-to-b from-yel/5 to-transparent p-4 md:p-5">
      <div className="flex items-baseline gap-2">
        <p className="text-[11px] font-bold tracking-widest text-yel uppercase">Right now</p>
        {today ? <p className="ml-auto text-[11px] text-tx3">{today}</p> : null}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {labels.map((label) => {
          const c = cardFor(label)
          return (
            <div
              key={label}
              data-testid="right-now-card"
              data-area={label}
              className="rounded-lg border-l-[3px] bg-bg2/80 px-4 py-3"
              style={{ borderColor: c.color }}
            >
              <p className="text-[10px] font-bold tracking-widest uppercase" style={{ color: c.color }}>
                {label}
              </p>
              <p className="mt-1 text-sm leading-snug text-tx">{c.text}</p>
            </div>
          )
        })}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
            Active A-PINs{' '}
            <span className="ml-1 rounded-lg bg-yel/15 px-1.5 py-0.5 text-yel">
              {rightNow.active_a_count || 0}
            </span>
          </p>
          <ActivePinList events={rightNow.active_a_pins} onOpenEvent={onOpenEvent} />
        </div>
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
            Active B-PINs{' '}
            <span className="ml-1 rounded-lg bg-[#14b8a6]/15 px-1.5 py-0.5 text-[#14b8a6]">
              {rightNow.active_b_count || 0}
            </span>
          </p>
          <ActivePinList events={rightNow.active_b_pins} onOpenEvent={onOpenEvent} />
        </div>
        <div>
          <p className="mb-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
            Next major deadline
          </p>
          {rightNow.next_major_deadline?.due ? (
            <div className="text-xs leading-snug text-tx">
              <p className="mb-1 font-bold text-yel">
                {rightNow.next_major_deadline.event_name}
              </p>
              <p>{rightNow.next_major_deadline.label}</p>
              <p className="mt-1 text-[10px] text-tx3">
                {rightNow.next_major_deadline.due} ·{' '}
                {deadlineDayLabel(today, rightNow.next_major_deadline.due)}
              </p>
            </div>
          ) : (
            <span className="text-tx3 italic">no upcoming deadlines</span>
          )}
        </div>
      </div>
    </section>
  )
}
