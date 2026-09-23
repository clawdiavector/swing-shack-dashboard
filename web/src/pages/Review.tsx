import { CalendarDays, Check, ImageIcon, Inbox, RotateCcw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, Button, PressIcon, QueueItem, StatCard, Tip } from '../components/ui'
import {
  fetchInbox,
  fetchPostingWeek,
  inboxAction,
  inboxChannelLabel,
  inboxGoesOutIso,
  inboxItemThumbUrl,
  inboxMediaTag,
  type InboxItem,
} from '../lib/api'
import {
  firstIncompleteStageFromStages,
  formatGoesOut,
  formatPostingDayHeader,
  nextActionFromStages,
  postingChannelLabel,
  postingWeekThumbUrl,
  POSTING_STAGE_LABELS,
  POSTING_STAGE_ORDER,
  type PostingStageKey,
  type PostingWeekDay,
  type PostingWeekPost,
} from '../lib/postingWeek'
import { reviewType } from '../lib/reviewType'
import { formatStamp } from '../lib/stamp'

type ReviewView = 'week' | 'inbox'

function itemType(item: InboxItem) {
  return (item.type || 'item').toLowerCase()
}

function ReviewInbox({ brandId }: { brandId: string }) {
  const [items, setItems] = useState<InboxItem[]>([])
  const [pending, setPending] = useState<number | null>(null)
  const [stale, setStale] = useState<number | null>(null)
  const [approved, setApproved] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filter, setFilter] = useState('all')

  function load() {
    fetchInbox('pending', brandId, 'draft_asset')
      .then((payload) => {
        setItems(payload.items || [])
        setPending(payload.counts?.pending ?? payload.items?.length ?? 0)
        setStale(payload.counts?.stale ?? 0)
        setApproved(payload.counts?.approved_today ?? 0)
      })
      .catch((err: Error) => setError(err.message))
  }

  useEffect(load, [brandId])

  async function act(id: string, action: 'approve' | 'reject') {
    setBusy(id)
    const result = await inboxAction(id, action)
    setBusy('')
    if (!result.ok) {
      setError(result.error || 'Action failed')
      return
    }
    load()
  }

  const types = useMemo(() => {
    const set = new Set(items.map(itemType))
    return ['all', 'has-image', 'no-image', 'no-brief', ...Array.from(set).sort()]
  }, [items])

  const shown =
    filter === 'all'
      ? items
      : filter === 'has-image' || filter === 'no-image' || filter === 'no-brief'
        ? items.filter((item) => inboxMediaTag(item).id === filter)
        : items.filter((item) => itemType(item) === filter)
  const first = shown[0]

  return (
    <div className="space-y-6">
      {error ? <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p> : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={Inbox} label="Pending" value={pending ?? '—'} hint="On your desk now" tone="gold" />
        <StatCard icon={RotateCcw} label="Stale" value={stale ?? '—'} hint="Sitting too long" tone="mute" />
        <StatCard icon={Check} label="Cleared today" value={approved ?? '—'} hint="Approved, not live" tone="green" />
      </div>

      <FilterChips
        value={filter}
        onChange={setFilter}
        options={types.map((id) => ({
          id,
          label:
            id === 'all'
              ? 'All'
              : id === 'has-image'
                ? 'Has image'
                : id === 'no-image'
                  ? 'No image'
                  : id === 'no-brief'
                    ? 'No brief'
                    : reviewType(id).label,
        }))}
      />

      {first ? (
        <section className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl border-[1.5px] border-ac/35 px-4 py-3 backdrop-blur-xl">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold tracking-wide text-tx3 uppercase">Next up</p>
            <p className="font-display text-lg font-semibold leading-snug">{first.title || first.summary}</p>
            <p className="text-xs text-tx3">
              {reviewType(first.type).label} · {first.brand_id || 'brand'} ·{' '}
              {formatStamp(first.created_at)}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Tip text="Mark this approved. It will not go live.">
              <button
                type="button"
                title="Mark this approved. It will not go live."
                disabled={busy === first.id}
                onClick={() => act(first.id, 'approve')}
                className="inline-flex items-center gap-1.5 rounded-full bg-ac px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-50"
              >
                <Check className="h-4 w-4" strokeWidth={2.5} />
                Approve
              </button>
            </Tip>
            <Tip text="Reject this and send it back to studio.">
              <button
                type="button"
                title="Reject this and send it back to studio."
                disabled={busy === first.id}
                onClick={() => act(first.id, 'reject')}
                className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-red hover:text-red"
              >
                <PressIcon icon={RotateCcw} className="h-4 w-4" />
                Send back
              </button>
            </Tip>
            <Button
              to={`/review/${encodeURIComponent(first.id)}`}
              icon={Inbox}
              tone="ghost"
              tip="Open this draft on its own page."
            >
              Open this piece
            </Button>
          </div>
        </section>
      ) : (
        <Button to="/create" icon={Sparkles} tip="Open Studio to start a new draft.">
          Go to studio
        </Button>
      )}

      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="font-display text-xl font-semibold">Queue</h2>
          <Badge tone="gold">{shown.length}</Badge>
        </div>
        <ul className="space-y-2">
          {shown.map((item) => {
            const thumb = inboxItemThumbUrl(item)
            const media = inboxMediaTag(item)
            const kind = reviewType(item.type).label
            const channel = inboxChannelLabel(item)
            const goesOut = inboxGoesOutIso(item)
            return (
              <QueueItem
                key={item.id}
                to={`/review/${encodeURIComponent(item.id)}`}
                badge={item.sla_state === 'stale' ? 'stale' : media.label}
                tone={item.sla_state === 'stale' ? 'gold' : media.tone}
                channelBadge={channel || undefined}
                title={item.title || item.summary || item.id}
                meta={[kind, item.brand_id, item.meta?.caption?.slice(0, 70)]
                  .filter(Boolean)
                  .join(' · ')}
                stamp={goesOut || item.created_at}
                stampKind={goesOut ? 'goes_out' : 'created'}
                dateOnly={Boolean(goesOut)}
                thumb={thumb || undefined}
                thumbAlt={item.title || item.id}
                action={
                  <Tip text="Mark this approved. It will not go live.">
                    <button
                      type="button"
                      title="Mark this approved. It will not go live."
                      disabled={busy === item.id}
                      onClick={(event) => {
                        event.preventDefault()
                        event.stopPropagation()
                        act(item.id, 'approve')
                      }}
                      className="shrink-0 text-xs font-semibold text-ac"
                    >
                      Approve
                    </button>
                  </Tip>
                }
              />
            )
          })}
          {shown.length === 0 ? (
            <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
              Nothing in this filter.
            </li>
          ) : null}
        </ul>
      </section>
    </div>
  )
}

function StageStepper({ stages }: { stages: Record<string, boolean> }) {
  const current = firstIncompleteStageFromStages(stages)
  return (
    <div
      className="flex min-w-0 flex-wrap items-start gap-y-2 pt-2"
      role="list"
      aria-label="Posting pipeline"
    >
      {POSTING_STAGE_ORDER.map((key, index) => {
        const done = Boolean(stages[key])
        const isCurrent = !done && key === current
        const lineDone =
          index > 0 &&
          POSTING_STAGE_ORDER.slice(0, index).every((prev) => Boolean(stages[prev]))
        return (
          <div key={key} className="flex min-w-0 items-center" role="listitem">
            {index > 0 ? (
              <span
                className={`mx-0.5 hidden h-px w-3 shrink-0 sm:block ${
                  lineDone ? 'bg-ac/70' : 'bg-bd'
                }`}
                aria-hidden
              />
            ) : null}
            <div className="flex min-w-[3.25rem] flex-col items-center gap-1 px-0.5">
              <span
                className={`flex h-2.5 w-2.5 shrink-0 items-center justify-center rounded-full ${
                  done
                    ? 'bg-ac text-bg'
                    : isCurrent
                      ? 'border-2 border-ac bg-bg-2 ring-2 ring-ac/25'
                      : 'border border-bd bg-transparent'
                }`}
                aria-hidden
              >
                {done ? <Check className="h-1.5 w-1.5" strokeWidth={3} /> : null}
              </span>
              <span
                className={`max-w-[4.5rem] text-center text-xs leading-tight ${
                  done ? 'font-medium text-tx' : isCurrent ? 'font-semibold text-tx' : 'text-tx3'
                }`}
              >
                {POSTING_STAGE_LABELS[key as PostingStageKey]}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function PostCardThumb({ imageUrl, title }: { imageUrl?: string | null; title: string }) {
  const [broken, setBroken] = useState(false)
  const src = postingWeekThumbUrl(imageUrl)
  const showImage = Boolean(src) && !broken
  return (
    <div
      className={`relative h-14 w-14 shrink-0 overflow-hidden rounded-xl border md:h-[4.5rem] md:w-[4.5rem] ${
        showImage ? 'border-bd bg-bg-2' : 'border-dashed border-bd bg-bg-2/50'
      }`}
    >
      {showImage ? (
        <img
          src={src!}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-tx3" aria-hidden>
          <ImageIcon className="h-5 w-5" strokeWidth={1.75} />
        </span>
      )}
      <span className="sr-only">{title}</span>
    </div>
  )
}

function PostCard({
  post,
  dayDate,
  weekday,
}: {
  post: PostingWeekPost
  dayDate: string
  weekday: string
}) {
  const clickable = Boolean(post.inbox_item_id)
  const channel = postingChannelLabel(post.primary_channel)
  const nextAction = nextActionFromStages(post.stages)
  const factLine = `${formatGoesOut(dayDate, weekday)} · ${nextAction}`

  const inner = (
    <div className="flex gap-3 md:items-start md:gap-4">
      <PostCardThumb imageUrl={post.image_url} title={post.title} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-col gap-0.5 md:flex-row md:items-start md:justify-between md:gap-3">
          <p className="truncate font-display text-base font-semibold leading-snug">{post.title}</p>
          {channel ? (
            <span className="shrink-0 text-xs font-medium text-tx2 md:text-right">{channel}</span>
          ) : null}
        </div>
        <p className="text-xs text-tx3">{factLine}</p>
        <StageStepper stages={post.stages} />
      </div>
    </div>
  )

  const shell = 'rounded-2xl border border-bd bg-bg-2/40 px-3 py-3 md:px-4'

  if (!clickable) {
    return <li className={`${shell} opacity-90`}>{inner}</li>
  }
  return (
    <li>
      <Link
        to={`/review/${encodeURIComponent(post.inbox_item_id || '')}`}
        className={`block ${shell} transition hover:border-ac/50`}
      >
        {inner}
      </Link>
    </li>
  )
}

function ReviewWeekBoard({ brandId }: { brandId: string }) {
  const [days, setDays] = useState<PostingWeekDay[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    fetchPostingWeek(brandId)
      .then((payload) => {
        if (!payload.ok) {
          setError(payload.error || 'Failed to load week board')
          return
        }
        setDays(payload.days_list || [])
        setError('')
      })
      .catch((err: Error) => setError(err.message))
  }, [brandId])

  if (error) {
    return (
      <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
    )
  }

  return (
    <div className="space-y-5">
      {days.map((day) => (
        <section key={day.date}>
          <div className="mb-2 flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-ac" strokeWidth={2} />
            <h2 className="font-display text-lg font-semibold">
              {formatPostingDayHeader(day)}
              {day.is_today ? (
                <span className="ml-2 text-xs font-semibold uppercase text-yel">Today</span>
              ) : null}
            </h2>
            <Badge tone="mute">{day.posts.length}</Badge>
          </div>
          {day.posts.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
              Nothing going out.
            </p>
          ) : (
            <ul className="space-y-2">
              {day.posts.map((post) => (
                <PostCard
                  key={post.calendar_id}
                  post={post}
                  dayDate={day.date}
                  weekday={day.weekday}
                />
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}

export function Review() {
  const { brandId: activeBrand } = useBrand()
  const brandId = activeBrand ?? 'swing-shack'
  const [searchParams, setSearchParams] = useSearchParams()
  const viewParam = searchParams.get('view')
  const view: ReviewView = viewParam === 'inbox' ? 'inbox' : 'week'

  function setView(next: ReviewView) {
    const nextParams = new URLSearchParams(searchParams)
    if (next === 'week') {
      nextParams.delete('view')
    } else {
      nextParams.set('view', 'inbox')
    }
    setSearchParams(nextParams, { replace: true })
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/review" title="Review — posting week">
        What goes out in the next seven days for this brand, plus the pending inbox.
      </PageIntro>

      <FilterChips
        value={view}
        onChange={(id) => setView(id as ReviewView)}
        options={[
          { id: 'week', label: 'This week' },
          { id: 'inbox', label: 'Inbox' },
        ]}
      />

      {view === 'week' ? <ReviewWeekBoard brandId={brandId} /> : <ReviewInbox brandId={brandId} />}
    </div>
  )
}
