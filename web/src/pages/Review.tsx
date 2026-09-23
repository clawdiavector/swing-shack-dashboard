import { CalendarDays, Check, Inbox, RotateCcw, Sparkles } from 'lucide-react'
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
  formatPostingDayHeader,
  POSTING_STAGE_LABELS,
  POSTING_STAGE_ORDER,
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

function StageChips({ stages }: { stages: Record<string, boolean> }) {
  return (
    <div className="flex flex-wrap gap-1">
      {POSTING_STAGE_ORDER.map((key) => {
        const done = Boolean(stages[key])
        return (
          <span
            key={key}
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              done ? 'bg-ac/20 text-ac' : 'bg-bg-2 text-tx3'
            }`}
          >
            {POSTING_STAGE_LABELS[key]}
          </span>
        )
      })}
    </div>
  )
}

function PostCard({ post }: { post: PostingWeekPost }) {
  const clickable = Boolean(post.inbox_item_id)
  const inner = (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-display text-base font-semibold leading-snug">{post.title}</p>
        {post.primary_channel ? (
          <Badge tone="mute">{String(post.primary_channel)}</Badge>
        ) : null}
      </div>
      <StageChips stages={post.stages} />
    </>
  )
  if (!clickable) {
    return (
      <li className="rounded-2xl border border-bd bg-bg-2/40 px-4 py-3 opacity-90">{inner}</li>
    )
  }
  return (
    <li>
      <Link
        to={`/review/${encodeURIComponent(post.inbox_item_id || '')}`}
        className="block rounded-2xl border border-bd px-4 py-3 transition hover:border-ac/50"
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
                <PostCard key={post.calendar_id} post={post} />
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
