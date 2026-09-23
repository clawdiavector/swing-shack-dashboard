import { Check, Library, Rocket, Send } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge, Button, QueueItem, StatCard, Tip } from '../components/ui'
import {
  enqueueSandboxItem,
  fetchInbox,
  fetchSandboxQueue,
  inboxChannelLabel,
  inboxGoesOutIso,
  inboxItemThumbUrl,
  inboxMediaTag,
  type InboxItem,
} from '../lib/api'
import { reviewType } from '../lib/reviewType'

export function Shelf() {
  const { brandId } = useBrand()
  const [items, setItems] = useState<InboxItem[]>([])
  const [queuedAssetIds, setQueuedAssetIds] = useState<Set<string>>(new Set())
  const [approvedCount, setApprovedCount] = useState<number | null>(null)
  const [clearedToday, setClearedToday] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  function load() {
    Promise.all([
      fetchInbox('approved', brandId, 'draft_asset'),
      fetchSandboxQueue(brandId),
    ])
      .then(([inbox, queue]) => {
        const ids = new Set<string>()
        for (const row of queue.items || []) {
          if (row.asset_id) ids.add(row.asset_id)
        }
        setQueuedAssetIds(ids)
        setItems(inbox.items || [])
        setApprovedCount(inbox.counts?.approved ?? inbox.items?.length ?? 0)
        setClearedToday(inbox.counts?.approved_today ?? null)
      })
      .catch((err: Error) => setError(err.message))
  }

  useEffect(load, [brandId])

  const onShelf = useMemo(
    () =>
      items.filter((item) => {
        const assetId = String(item.meta?.asset_id || '')
        return assetId && !queuedAssetIds.has(assetId)
      }),
    [items, queuedAssetIds],
  )

  async function handleQueue(item: InboxItem) {
    const assetId = String(item.meta?.asset_id || '')
    const brand = String(item.brand_id || brandId || '')
    const caption = String(item.meta?.caption || item.summary || '')
    if (!assetId || !brand) {
      setError('Missing asset or brand for sandbox enqueue')
      return
    }
    setBusy(item.id)
    setError('')
    const { status, data } = await enqueueSandboxItem({
      brand_id: brand,
      asset_id: assetId,
      caption_preview: caption,
      inbox_item_id: item.id,
    })
    setBusy('')
    if (status >= 400 || !data.ok) {
      setError(data.error || 'Could not queue to sandbox')
      return
    }
    load()
  }

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Library}
        here="/shelf"
        title="On the shelf"
      >
        Approved drafts sitting here — not queued, not live. Push to Publish when ready.
      </PageIntro>

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <StatCard
          icon={Check}
          label="Approved on shelf"
          value={onShelf.length}
          hint="Not in sandbox queue"
          tone="green"
        />
        <StatCard
          icon={Rocket}
          label="Cleared today"
          value={clearedToday ?? '—'}
          hint="Matches Review"
          tone="mute"
        />
      </div>

      <p className="text-xs text-tx3">
        Approved, not queued. Not live. {approvedCount != null ? `${approvedCount} approved draft(s) total.` : ''}
      </p>

      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="font-display text-xl font-semibold">Shelf</h2>
          <Badge tone="green">{onShelf.length}</Badge>
        </div>
        <ul className="space-y-2">
          {onShelf.map((item) => {
            const thumb = inboxItemThumbUrl(item)
            const media = inboxMediaTag(item)
            const kind = reviewType(item.type).label
            const channel = inboxChannelLabel(item)
            const goesOut = inboxGoesOutIso(item)
            return (
              <QueueItem
                key={item.id}
                to={`/review/${encodeURIComponent(item.id)}`}
                badge={media.label}
                tone={media.tone}
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
                  <Tip text="Copy caption onto the sandbox publish queue. Does not go live.">
                    <button
                      type="button"
                      title="Queue to sandbox publish"
                      disabled={busy === item.id}
                      onClick={(event) => {
                        event.preventDefault()
                        event.stopPropagation()
                        handleQueue(item)
                      }}
                      className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-ac"
                    >
                      <Send className="h-3.5 w-3.5" strokeWidth={2.5} />
                      Queue
                    </button>
                  </Tip>
                }
              />
            )
          })}
          {onShelf.length === 0 ? (
            <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
              Nothing on the shelf — approve drafts in Review first.
            </li>
          ) : null}
        </ul>
      </section>

      <Button to="/publish" icon={Send} tip="Open Publish to see the sandbox queue.">
        Open publish
      </Button>
    </div>
  )
}
