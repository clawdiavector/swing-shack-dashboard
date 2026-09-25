import { Check, Inbox, RotateCcw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { BrandChip } from '../components/BrandChip'
import { ReviewDraftDetail } from '../components/ReviewDraftDetail'
import { useBrandScope } from '../components/BrandSwitch'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, Button, QueueItem, StatCard, Tip } from '../components/ui'
import {
  draftRegeneratePhoto,
  draftRecompose,
  draftSwapCandidate,
  fetchBrandImagesToday,
  fetchInbox,
  inboxAction,
  inboxChannelLabel,
  inboxGoesOutIso,
  inboxItemThumbUrl,
  inboxMediaTag,
  reviewPiecePath,
  type InboxItem,
} from '../lib/api'
import { dedupeById } from '../lib/dedupeById'
import { fanOutPayloads, type FanOutFailure } from '../lib/fanOut'
import { sumCounts } from '../lib/mergeCounts'
import { reviewType } from '../lib/reviewType'
import { useLoadGate } from '../lib/useLoadGate'
function itemType(item: InboxItem) {
  return (item.type || 'item').toLowerCase()
}

function ReviewInbox({
  brandId,
  isAll,
  brandIds,
}: {
  brandId: string
  isAll: boolean
  brandIds: string[]
}) {
  const [items, setItems] = useState<InboxItem[]>([])
  const [pending, setPending] = useState<number | null>(null)
  const [stale, setStale] = useState<number | null>(null)
  const [approved, setApproved] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filter, setFilter] = useState('all')
  const [failures, setFailures] = useState<FanOutFailure[]>([])
  const [imageCap, setImageCap] = useState<{ at_cap: boolean; cap: number } | null>(null)
  const [draftBusy, setDraftBusy] = useState(false)
  const { trackLoad, waitForLoad } = useLoadGate()

  function load() {
    const run = async (): Promise<void> => {
      setFailures([])
      if (isAll) {
        const { payloads, failures: fails } = await fanOutPayloads(brandIds, (bid) =>
          fetchInbox('pending', bid, 'draft_asset'),
        )
        setFailures(fails)
        const mergedRaw = payloads.flatMap(({ brandId: bid, payload }) =>
          (payload.items || []).map((item) => ({
            ...item,
            brand_id: item.brand_id ?? bid,
          })),
        )
        const merged = dedupeById(mergedRaw)
        merged.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
        setItems(merged)
        const counts = sumCounts(payloads.map((p) => p.payload.counts))
        setPending(counts.pending ?? merged.length)
        setStale(counts.stale ?? 0)
        setApproved(counts.approved_today ?? 0)
        setError('')
        return
      }
      fetchInbox('pending', brandId, 'draft_asset')
        .then((payload) => {
          setItems(payload.items || [])
          setPending(payload.counts?.pending ?? payload.items?.length ?? 0)
          setStale(payload.counts?.stale ?? 0)
          setApproved(payload.counts?.approved_today ?? 0)
        })
        .catch((err: Error) => setError(err.message))
    }
    trackLoad(run())
  }

  useEffect(load, [brandId, isAll, brandIds, trackLoad])

  async function act(id: string, action: 'approve' | 'reject', reason = '') {
    setBusy(id)
    await waitForLoad()
    const result = await inboxAction(id, action, reason)
    setBusy('')
    if (!result.ok) {
      setError(result.error || 'Action failed')
      return
    }
    load()
  }

  const types = useMemo(() => ['all', 'no-brief'], [])

  const shown =
    filter === 'all'
      ? items
      : filter === 'no-brief'
        ? items.filter((item) => inboxMediaTag(item).id === filter)
        : items.filter((item) => itemType(item) === filter)

  const firstDraft = shown[0]
  const firstDraftBrand = firstDraft?.brand_id

  useEffect(() => {
    setImageCap(null)
    if (!firstDraftBrand) return
    let live = true
    fetchBrandImagesToday(firstDraftBrand)
      .then((payload) => {
        if (!live) return
        setImageCap({ at_cap: Boolean(payload.at_cap), cap: payload.cap ?? 2 })
      })
      .catch(() => {
        if (live) setImageCap(null)
      })
    return () => {
      live = false
    }
  }, [firstDraftBrand])

  const atImageCap = Boolean(imageCap?.at_cap)
  const regenerateTip = atImageCap
    ? `Daily image cap reached for ${firstDraftBrand || 'brand'}`
    : 'Queue a new draft photo with a corrective note (P4 API — not the image router).'

  async function runDraftAction(run: () => Promise<boolean>) {
    setDraftBusy(true)
    setError('')
    await waitForLoad()
    try {
      const ok = await run()
      if (ok) load()
    } finally {
      setDraftBusy(false)
    }
  }

  function mergeComposedOntoFirst(composed?: Record<string, string>) {
    if (!composed || !firstDraft) return
    setItems((prev) =>
      prev.map((row) =>
        row.id === firstDraft.id
          ? {
              ...row,
              meta: {
                ...row.meta,
                composed: { ...row.meta?.composed, ...composed },
                image_url: composed[firstDraft.meta?.primary_channel || 'instagram'] || row.meta?.image_url,
              },
            }
          : row,
      ),
    )
  }

  return (
    <div className="space-y-6">
      <PartialBrandLoadStrip failures={failures} onRetry={load} />
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
            id === 'all' ? 'All' : id === 'no-brief' ? 'No brief' : reviewType(id).label,
        }))}
      />

      {firstDraft && itemType(firstDraft) === 'draft_asset' ? (
        <ReviewDraftDetail
          item={firstDraft}
          showBrandChip={isAll}
          atImageCap={atImageCap}
          regenerateTip={regenerateTip}
          busy={draftBusy || busy === firstDraft.id}
          onApprove={() => void act(firstDraft.id, 'approve')}
          onReject={(reason) => void act(firstDraft.id, 'reject', reason)}
          onRegenerate={(note) =>
            void runDraftAction(async () => {
              const result = await draftRegeneratePhoto(firstDraft.id, note)
              if (result.at_cap) {
                setImageCap({ at_cap: true, cap: imageCap?.cap ?? 2 })
              }
              if (!result.ok) {
                setError(result.error || 'Regenerate failed')
                return false
              }
              return true
            })
          }
          onRecomposeHeadline={(headline) =>
            void runDraftAction(async () => {
              const result = await draftRecompose(firstDraft.id, { headline })
              if (!result.ok) {
                setError(result.error || 'Recompose failed')
                return false
              }
              mergeComposedOntoFirst(result.composed)
              return true
            })
          }
          onSwapCandidate={(candidateIndex) =>
            void runDraftAction(async () => {
              const result = await draftSwapCandidate(firstDraft.id, candidateIndex)
              if (!result.ok) {
                setError(result.error || 'Swap failed')
                return false
              }
              mergeComposedOntoFirst(result.composed)
              return true
            })
          }
        />
      ) : firstDraft ? (
        <section className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl border-[1.5px] border-ac/35 px-4 py-3 backdrop-blur-xl">
          <div className="min-w-0">
            <p className="font-display text-lg font-semibold leading-snug">{firstDraft.title || firstDraft.summary}</p>
          </div>
          <Button
            to={reviewPiecePath(firstDraft.id, firstDraft.brand_id)}
            icon={Inbox}
            tone="ghost"
            tip="Open this draft on its own page."
          >
            Open this piece
          </Button>
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
            const kind = reviewType(item.type).label
            const channel = inboxChannelLabel(item)
            const goesOut = inboxGoesOutIso(item)
            const stateChip =
              item.sla_state === 'stale'
                ? 'Stale'
                : item.status
                  ? item.status.replace(/_/g, ' ')
                  : item.meta?.approval_status || 'Pending'
            return (
              <QueueItem
                key={item.id}
                to={reviewPiecePath(item.id, item.brand_id)}
                typeBadge={kind}
                stateBadge={stateChip}
                hideImageFallbackBadge
                channelBadge={channel || undefined}
                title={item.title || item.summary || item.id}
                meta={[item.meta?.caption?.slice(0, 70)].filter(Boolean).join(' · ')}
                footer={isAll ? <BrandChip brandId={item.brand_id} show /> : undefined}
                stamp={goesOut || item.created_at}
                stampKind={goesOut ? 'goes_out' : 'created'}
                dateOnly={Boolean(goesOut)}
                thumb={thumb || undefined}
                thumbAlt={item.title || item.id}
                thumbClassName="h-[120px] w-[120px] shrink-0 rounded-xl border border-bd object-cover"
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

export function Review() {
  const { isAll, brandIds, scope } = useBrandScope()
  const brandId = scope === 'all' ? 'swing-shack' : scope
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  useEffect(() => {
    const view = searchParams.get('view')
    if (view === 'week') {
      navigate('/week', { replace: true })
    } else if (view === 'inbox') {
      navigate('/inbox', { replace: true })
    }
  }, [searchParams, navigate])

  return (
    <div className="space-y-6">
      <PageIntro here="/review" title="Review — drafts">
        Draft-ready posts on your desk. Candidates live on{' '}
        <Link to="/inbox" className="font-semibold text-ac hover:underline">
          Inbox
        </Link>
        ; the posting week is on{' '}
        <Link to="/week" className="font-semibold text-ac hover:underline">
          This week
        </Link>
        .
      </PageIntro>

      <ReviewInbox brandId={brandId} isAll={isAll} brandIds={brandIds} />
    </div>
  )
}
