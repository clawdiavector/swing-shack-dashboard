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
  rightNow,
  onOpenEvent,
}: {
  brand: string
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

  return (
    <section className="glass space-y-4 rounded-2xl border border-yel/20 bg-gradient-to-b from-yel/5 to-transparent p-4 md:p-5">
      <div className="flex items-baseline gap-2">
        <p className="text-[11px] font-bold tracking-widest text-yel uppercase">Right now</p>
        {today ? <p className="ml-auto text-[11px] text-tx3">{today}</p> : null}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {(
          [
            ['RETAIL', '#f0a030', rn.retail || 'Steady new arrivals + walk-in retail.'],
            ['FITTING', '#14b8a6', rn.fitting || 'Iron / wedge / putter fitting on-ramp.'],
            ['COACHING', '#f0a030', rn.coaching || 'Lessons + playing-coach sessions.'],
          ] as const
        ).map(([label, color, text]) => (
          <div
            key={label}
            className="rounded-lg border-l-[3px] bg-bg2/80 px-4 py-3"
            style={{ borderColor: color }}
          >
            <p className="text-[10px] font-bold tracking-widest uppercase" style={{ color }}>
              {label}
            </p>
            <p className="mt-1 text-sm leading-snug text-tx">{text}</p>
          </div>
        ))}
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
