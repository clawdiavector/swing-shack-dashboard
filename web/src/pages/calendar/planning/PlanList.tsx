import { Loader2 } from 'lucide-react'
import { PIN_COLORS } from '../../../lib/planning'
import type { PlanningEventDetail, PlanningTimelineEvent } from '../../../lib/planningTypes'
import { EventDetail } from './EventDetail'
import { useBrief } from './PlanningContextModal'

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

// Typed entries the Brief engine refuses by design; they are dates to
// remember, not campaigns, so the row offers no Brief step.
const NO_BRIEF_TYPES: Record<string, string> = {
  moment: 'Moment',
  content: 'Content',
  reminder: 'Reminder',
}

function eventStart(ev: PlanningTimelineEvent): string {
  return ev.start || ev.public_peak || ev.planning_start || ''
}

export function formatPlanDate(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)} ${d.getFullYear()}`
}

function monthHeading(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  if (!iso || Number.isNaN(d.getTime())) return 'No date yet'
  return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** The one next step for an entry on the calendar: create its Brief, or open it. */
function NextStep({ brandId, ev }: { brandId: string; ev: PlanningTimelineEvent }) {
  const eventKey = ev.event_key || ev.id
  const { briefId, busy, refused, error, createBrief, briefUrl } = useBrief({
    brandId,
    eventKey,
    knownBriefId: ev.brief_id || '',
    lookup: false,
  })
  // A scheduled post is already made; it is not something to brief.
  const noBrief = ev.post_type ? 'Scheduled post' : NO_BRIEF_TYPES[ev.type || '']

  if (briefId) {
    return (
      <a
        href={briefUrl(briefId)}
        target="_blank"
        rel="noreferrer"
        data-testid="plan-open-brief"
        className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/25"
      >
        Open brief
      </a>
    )
  }
  if (noBrief) {
    return (
      <span
        className="shrink-0 px-3 py-1.5 text-xs text-tx3"
        title={
          ev.post_type
            ? 'A post that is already scheduled for this day.'
            : 'Briefs are written for campaigns. To brief this, suggest it again as a Campaign.'
        }
      >
        {noBrief}
      </span>
    )
  }
  return (
    <span className="flex shrink-0 flex-col items-end gap-1">
      <button
        type="button"
        disabled={busy || !eventKey || !brandId}
        onClick={() => void createBrief()}
        data-testid="plan-create-brief"
        className="inline-flex items-center gap-1.5 rounded-full border border-yel/40 bg-yel/15 px-3 py-1.5 text-xs font-semibold text-yel hover:bg-yel/25 disabled:opacity-60"
      >
        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
        {busy ? 'Creating…' : 'Create brief'}
      </button>
      {refused ? (
        <span className="max-w-[16rem] text-right text-[11px] text-tx3" data-testid="plan-brief-refused">
          {refused.title}
          {refused.reasons.length ? ` ${refused.reasons.join(' ')}` : ''}
        </span>
      ) : null}
      {error ? <span className="max-w-[16rem] text-right text-[11px] text-red">{error}</span> : null}
    </span>
  )
}

/** Everything on the calendar from today to 12 months out, soonest first, one row each. */
export function PlanList({
  brandId,
  events,
  eventDetail,
  onOpenEvent,
  onCloseEvent,
}: {
  brandId: string
  events: PlanningTimelineEvent[]
  eventDetail: PlanningEventDetail | null
  onOpenEvent: (id: string) => void
  onCloseEvent: () => void
}) {
  const rows = [...events].sort((a, b) => {
    const da = eventStart(a) || '9999'
    const db = eventStart(b) || '9999'
    return da.localeCompare(db) || (a.name || '').localeCompare(b.name || '')
  })
  if (!rows.length) {
    return (
      <p className="rounded-lg border border-dashed border-bd px-4 py-6 text-sm text-tx3">
        Nothing on the calendar in the next 12 months.
      </p>
    )
  }
  const openId = eventDetail?.event?.id
  let lastHeading = ''
  return (
    <ul className="space-y-1" data-testid="plan-list">
      {rows.map((ev) => {
        const tier = ev.tier || 'C-PIN'
        const c = PIN_COLORS[tier] || PIN_COLORS['C-PIN']
        const start = eventStart(ev)
        const end = ev.end && ev.end !== start ? ev.end : ''
        const heading = monthHeading(start)
        const showHeading = heading !== lastHeading
        lastHeading = heading
        const open = openId === ev.id
        return (
          <li key={ev.id}>
            {showHeading ? (
              <p className="px-1 pt-4 pb-1 text-[11px] font-bold tracking-widest text-tx3 uppercase">
                {heading}
              </p>
            ) : null}
            <div
              className="flex items-center gap-3 rounded-md bg-bg2 px-3 py-2"
              data-testid="plan-list-row"
            >
              <button
                type="button"
                onClick={() => (open ? onCloseEvent() : onOpenEvent(ev.id))}
                aria-expanded={open}
                className="grid min-w-0 flex-1 grid-cols-[6.5rem_4rem_1fr] items-baseline gap-3 text-left hover:text-yel sm:grid-cols-[11.5rem_4rem_1fr]"
              >
                <span className="text-xs font-semibold text-tx2">
                  {start ? formatPlanDate(start) : 'No date yet'}
                  {end ? ` – ${formatPlanDate(end)}` : ''}
                </span>
                <span
                  className="justify-self-start rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
                  style={{ background: c.bg, color: c.fg }}
                >
                  {tier}
                </span>
                <span className="min-w-0">
                  <span className="text-sm font-bold text-tx">
                    {ev.name || '(untitled)'}
                    {ev.shopping_moment ? ' 🛍' : ''}
                  </span>
                  {ev.category ? <span className="ml-2 text-[11px] text-tx3">{ev.category}</span> : null}
                  {ev.commercial_push ? (
                    <span className="mt-0.5 block truncate text-xs text-tx3">{ev.commercial_push}</span>
                  ) : null}
                </span>
              </button>
              <NextStep brandId={brandId} ev={ev} />
            </div>
            {open ? <EventDetail data={eventDetail} onClose={onCloseEvent} /> : null}
          </li>
        )
      })}
    </ul>
  )
}
