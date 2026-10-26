import type { DayPrimaryPost, PillarOption, Suggestion } from '../../../lib/calendarSuggestions'
import { suggestionsUnderPrimary } from '../../../lib/calendarSuggestions'
import { GhostChip } from './MonthSuggestions'

export function PrimaryPostChip({ post }: { post: DayPrimaryPost }) {
  return (
    <span
      className="inline-flex max-w-full items-center gap-1 truncate rounded-full border border-ac/50 bg-ac/15 px-2 py-0.5 text-[10.5px] font-semibold text-ac"
      data-testid="primary-post-chip"
      title={post.state ? `${post.title} (${post.state})` : post.title}
    >
      {post.title}
    </span>
  )
}

export function DayPostSuggestions({
  iso,
  postsByDay,
  ghosts,
  busyKey,
  pillars,
  onApprove,
  onReject,
  onSwap,
}: {
  iso: string
  postsByDay: Record<string, DayPrimaryPost[]>
  ghosts: Suggestion[]
  busyKey: string | null
  pillars: PillarOption[]
  onApprove: (s: Suggestion, pillar: string) => void
  onReject: (s: Suggestion) => void
  onSwap?: (s: Suggestion) => void
}) {
  const { primary, secondary, showMoreLabel } = suggestionsUnderPrimary(iso, postsByDay, ghosts)
  if (!primary.length && !secondary.length) return null

  return (
    <div className="flex flex-col gap-0.5" data-testid="day-post-suggestions">
      {primary.map((p) => (
        <PrimaryPostChip key={`${p.calendar_id || p.title}`} post={p} />
      ))}
      {showMoreLabel ? (
        <p className="pt-0.5 text-[8px] font-bold tracking-wide text-tx3 uppercase" data-testid="more-ideas-label">
          More ideas for this day
        </p>
      ) : null}
      {secondary.map((g) => (
        <GhostChip
          key={g.key}
          s={g}
          busy={busyKey === g.key}
          pillars={pillars}
          compact={primary.length > 0}
          onApprove={(pillar) => onApprove(g, pillar)}
          onReject={() => onReject(g)}
          onSwap={g.source === 'stock' && onSwap ? () => onSwap(g) : undefined}
        />
      ))}
    </div>
  )
}
