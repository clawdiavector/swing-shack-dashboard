import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import '../../../fun.css'
import { Mascot } from '../../../components/fun'
import { EventTypeIcon, EventTypeLegend } from '../../../components/EventTypeIcon'
import { PIN_COLORS, plainCategory, plainNotes, tierLabel } from '../../../lib/planning'
import type { PlanningEventDetail, PlanningTimelineEvent } from '../../../lib/planningTypes'
import { EventDetail } from './EventDetail'
import { PlanPanel } from './PlanPanel'
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

/** "today", "tomorrow", "in 12 days", "3 days ago", or '' when the date is missing. */
function whenLabel(iso: string, endIso = ''): string {
  if (!iso) return ''
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const days = Math.round((d.getTime() - now.getTime()) / 86400000)
  if (days < 0 && endIso) {
    const e = new Date(`${endIso.slice(0, 10)}T00:00:00`)
    if (!Number.isNaN(e.getTime()) && e.getTime() >= now.getTime()) return 'On now'
  }
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days === -1) return 'Yesterday'
  if (days > 0) return days < 60 ? `In ${days} days` : `In ${Math.round(days / 30)} months`
  return `${-days} days ago`
}

type BriefState = ReturnType<typeof useBrief>

/** The one next step for an entry on the calendar: create its Brief, or open it and its plan. */
function NextStep({
  brandId,
  ev,
  brief,
  planOpen,
  onTogglePlan,
}: {
  brandId: string
  ev: PlanningTimelineEvent
  brief: BriefState
  planOpen: boolean
  onTogglePlan: () => void
}) {
  const eventKey = ev.event_key || ev.id
  const { briefId, busy, refused, error, createBrief, briefUrl } = brief
  // A scheduled post is already made; it is not something to brief.
  const noBrief = ev.note_only
    ? 'Date to note'
    : ev.post_type
      ? 'Scheduled post'
      : NO_BRIEF_TYPES[ev.type || '']

  if (briefId) {
    return (
      <span className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={onTogglePlan}
          aria-expanded={planOpen}
          data-testid="plan-open-plan"
          className="fun-btn rounded-full border border-yel/40 bg-yel/15 px-3 py-1.5 text-xs font-semibold text-yel hover:bg-yel/25"
        >
          {planOpen ? 'Hide plan' : 'Plan'}
        </button>
        <a
          href={briefUrl(briefId)}
          target="_blank"
          rel="noreferrer"
          data-testid="plan-open-brief"
          className="fun-btn rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/25"
        >
          Open brief
        </a>
      </span>
    )
  }
  if (noBrief) {
    return (
      <span
        className="shrink-0 px-3 py-1.5 text-xs text-tx3"
        title={
          ev.note_only
            ? 'From your list of important dates. Use New date or campaign to plan something for it.'
            : ev.post_type
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
        className="fun-btn inline-flex items-center gap-1.5 rounded-full border border-yel/40 bg-yel/15 px-3 py-1.5 text-xs font-semibold text-yel hover:bg-yel/25 disabled:opacity-60"
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

/** One calendar entry: its dates, its next step, and (once briefed) its plan. */
function PlanRow({
  brandId,
  ev,
  open,
  startPlanOpen = false,
  heading,
  headingCount,
  eventDetail,
  onOpenEvent,
  onCloseEvent,
}: {
  brandId: string
  ev: PlanningTimelineEvent
  open: boolean
  startPlanOpen?: boolean
  heading: string | null
  headingCount?: number
  eventDetail: PlanningEventDetail | null
  onOpenEvent: (id: string) => void
  onCloseEvent: () => void
}) {
  const brief = useBrief({
    brandId,
    eventKey: ev.event_key || ev.id,
    knownBriefId: ev.brief_id || '',
    lookup: true,
  })
  const [planOpen, setPlanOpen] = useState(startPlanOpen)
  const tier = ev.tier || 'C-PIN'
  const c = PIN_COLORS[tier] || PIN_COLORS['C-PIN']
  const start = eventStart(ev)
  const end = ev.end && ev.end !== start ? ev.end : ''
  return (
    <li>
      {heading ? (
        <p className="flex items-center gap-2 px-1 pt-5 pb-1.5 font-display text-lg font-extrabold">
          {heading}
          {headingCount ? <span className="fun-count">{headingCount}</span> : null}
        </p>
      ) : null}
      <div className="fun-lift flex items-center gap-3 rounded-2xl border border-bd bg-bg2 px-3 py-2.5" data-testid="plan-list-row">
        <button
          type="button"
          disabled={ev.note_only}
          onClick={() => (open ? onCloseEvent() : onOpenEvent(ev.id))}
          aria-expanded={ev.note_only ? undefined : open}
          className="grid min-w-0 flex-1 grid-cols-[6.5rem_4rem_1fr] items-baseline gap-3 text-left enabled:hover:text-yel sm:grid-cols-[11.5rem_4rem_1fr]"
        >
          <span className="text-xs font-semibold text-tx2">
            {start ? formatPlanDate(start) : 'No date yet'}
            {end ? ` – ${formatPlanDate(end)}` : ''}
            {whenLabel(start, end) ? (
              <span className="fun-when" data-past={whenLabel(start, end).endsWith('ago') || whenLabel(start, end) === 'Yesterday' ? 'true' : undefined}>
                {whenLabel(start, end)}
              </span>
            ) : null}
          </span>
          <span
            className="justify-self-start rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
            style={{ background: c.bg, color: c.fg }}
          >
            {tierLabel(tier)}
          </span>
          <span className="min-w-0">
            <EventTypeIcon kind={ev.kind} className="mr-1.5 align-middle" />
            <span className="text-sm font-bold text-tx">
              {ev.name || '(untitled)'}
            </span>
            {ev.local ? (
              <span className="ml-2 rounded bg-ac/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-ac uppercase">
                Local
              </span>
            ) : null}
            {plainCategory(ev.category) ? <span className="ml-2 text-[11px] text-tx3">{plainCategory(ev.category)}</span> : null}
            {ev.commercial_push ? (
              <span className="mt-0.5 block truncate text-xs text-tx3">{plainNotes(ev.commercial_push)}</span>
            ) : null}
          </span>
        </button>
        <NextStep
          brandId={brandId}
          ev={ev}
          brief={brief}
          planOpen={planOpen}
          onTogglePlan={() => setPlanOpen((v) => !v)}
        />
      </div>
      {open ? <EventDetail data={eventDetail} onClose={onCloseEvent} /> : null}
      {planOpen && brief.briefId ? (
        <div className="mt-1 rounded-md border border-bd">
          <PlanPanel brandId={brandId} briefId={brief.briefId} />
        </div>
      ) : null}
    </li>
  )
}

/** Everything on the calendar from today to 12 months out, soonest first, one row each. */
function eventMatchesFocus(ev: PlanningTimelineEvent, focus: string): boolean {
  if (!focus) return false
  const f = focus.trim().toLowerCase()
  return [ev.event_key, ev.id, ev.brief_id, ev.name].some((v) => String(v || '').trim().toLowerCase() === f)
}

export function PlanList({
  brandId,
  events,
  eventDetail,
  onOpenEvent,
  onCloseEvent,
  focusEvent = '',
}: {
  brandId: string
  events: PlanningTimelineEvent[]
  eventDetail: PlanningEventDetail | null
  onOpenEvent: (id: string) => void
  onCloseEvent: () => void
  /** From ?event= / ?brief= — open this row's plan. */
  focusEvent?: string
}) {
  const rows = [...events].sort((a, b) => {
    const da = eventStart(a) || '9999'
    const db = eventStart(b) || '9999'
    return da.localeCompare(db) || (a.name || '').localeCompare(b.name || '')
  })
  if (!rows.length) {
    return (
      <p className="fun-empty">
        <Mascot tone="blue" />
        <span>Nothing on the calendar in the next 12 months. A blank page. Fill it up!</span>
      </p>
    )
  }
  const openId = eventDetail?.event?.id
  const headingCounts: Record<string, number> = {}
  for (const r of rows) {
    const h = monthHeading(eventStart(r))
    headingCounts[h] = (headingCounts[h] || 0) + 1
  }
  let lastHeading = ''
  return (
    <>
    <EventTypeLegend className="pb-2" />
    <ul className="space-y-2" data-testid="plan-list">
      {rows.map((ev) => {
        const heading = monthHeading(eventStart(ev))
        const showHeading = heading !== lastHeading
        lastHeading = heading
        return (
          <PlanRow
            key={ev.id}
            brandId={brandId}
            ev={ev}
            open={openId === ev.id}
            startPlanOpen={eventMatchesFocus(ev, focusEvent)}
            heading={showHeading ? heading : null}
            headingCount={showHeading ? headingCounts[heading] : undefined}
            eventDetail={eventDetail}
            onOpenEvent={onOpenEvent}
            onCloseEvent={onCloseEvent}
          />
        )
      })}
    </ul>
    </>
  )
}
