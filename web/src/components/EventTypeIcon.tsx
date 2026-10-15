import { CalendarCheck, CalendarRange, CircleDot, Flag, ShoppingBag, Trophy, type LucideIcon } from 'lucide-react'

export type EventKind = 'retail_push' | 'sport_event' | 'service_push' | 'season' | 'light' | 'standard'

type TypeInfo = { label: string; hint: string; icon: LucideIcon; tone: string }

/** One icon and colour per kind of date, so a row can be told apart at a glance.
 *  The kinds are the same ones that shape a plan. */
export const EVENT_TYPES: Record<EventKind, TypeInfo> = {
  retail_push: {
    label: 'Retail',
    hint: 'A shopping moment: product, offers, a run of posts',
    icon: ShoppingBag,
    tone: 'text-amber-400 bg-amber-400/15 border-amber-400/40',
  },
  sport_event: {
    label: 'Sport',
    hint: 'A sporting event: build-up, game day, reaction',
    icon: Trophy,
    tone: 'text-emerald-400 bg-emerald-400/15 border-emerald-400/40',
  },
  service_push: {
    label: 'Fitting and coaching',
    hint: 'A push for bookings',
    icon: CalendarCheck,
    tone: 'text-teal-300 bg-teal-300/15 border-teal-300/40',
  },
  season: {
    label: 'Season',
    hint: 'Runs for weeks: a steady post each week',
    icon: CalendarRange,
    tone: 'text-violet-400 bg-violet-400/15 border-violet-400/40',
  },
  light: {
    label: 'Small date',
    hint: 'A smaller date: one post and a story',
    icon: CircleDot,
    tone: 'text-slate-400 bg-slate-400/10 border-slate-400/30',
  },
  standard: {
    label: 'General',
    hint: 'No special type',
    icon: Flag,
    tone: 'text-sky-300 bg-sky-300/15 border-sky-300/40',
  },
}

export const EVENT_KIND_ORDER: EventKind[] = [
  'retail_push',
  'sport_event',
  'service_push',
  'season',
  'light',
  'standard',
]

export function eventTypeInfo(kind?: string | null): TypeInfo {
  return EVENT_TYPES[(kind as EventKind) in EVENT_TYPES ? (kind as EventKind) : 'standard']
}

/** A small round badge with the icon for a kind of date. Never colour alone:
 *  it has a hover title and a screen-reader label. `withLabel` adds the word. */
export function EventTypeIcon({
  kind,
  size = 'md',
  withLabel = false,
  className = '',
}: {
  kind?: string | null
  size?: 'sm' | 'md'
  withLabel?: boolean
  className?: string
}) {
  const t = eventTypeInfo(kind)
  const Icon = t.icon
  const px = size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5'
  return (
    <span
      role="img"
      aria-label={`${t.label}: ${t.hint}`}
      title={`${t.label}: ${t.hint}`}
      data-testid="event-type-icon"
      data-kind={kind || 'standard'}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border ${
        withLabel ? 'px-2 py-0.5' : size === 'sm' ? 'p-0.5' : 'p-1'
      } text-[10px] leading-none font-bold tracking-wide ${t.tone} ${className}`}
    >
      <Icon className={px} strokeWidth={2.25} aria-hidden />
      {withLabel ? t.label : null}
    </span>
  )
}

/** A key to the icons, for the top of a view. */
export function EventTypeLegend({ className = '' }: { className?: string }) {
  return (
    <ul className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-tx3 ${className}`} data-testid="event-type-legend">
      {EVENT_KIND_ORDER.map((k) => (
        <li key={k} className="inline-flex items-center gap-1" title={EVENT_TYPES[k].hint}>
          <EventTypeIcon kind={k} size="sm" />
          {EVENT_TYPES[k].label}
        </li>
      ))}
    </ul>
  )
}
