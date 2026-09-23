import { ArrowLeft, Check, Pencil, RotateCcw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge, Button, PressIcon, QueueItem, Tip } from '../components/ui'
import {
  assetVisualUrl,
  fetchCampaign,
  fetchInbox,
  fetchInboxItem,
  inboxAction,
  type CampaignAsset,
  type InboxItem,
} from '../lib/api'
import { formatStamp } from '../lib/stamp'
import { toolTo } from '../lib/tools'

function studioTo(item: InboxItem) {
  const asset = item.meta?.asset_id
  const campaign = item.meta?.campaign_id
  const extra = {
    item: item.id,
    asset,
    campaign,
    title: item.title || item.summary,
    from: `/review/${encodeURIComponent(item.id)}`,
  }
  if (item.type === 'publish_request') return toolTo('publish', extra)
  if (item.type === 'calendar_candidate') return toolTo('calendar', extra)
  return toolTo('buildpost', extra)
}

export function ReviewPiece() {
  const { brandId } = useBrand()
  const { itemId = '' } = useParams()
  const id = decodeURIComponent(itemId)
  const navigate = useNavigate()
  const [item, setItem] = useState<InboxItem | null>(null)
  const [queue, setQueue] = useState<InboxItem[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [asset, setAsset] = useState<CampaignAsset | null>(null)
  const [assetErr, setAssetErr] = useState('')
  const [assetLoading, setAssetLoading] = useState(false)
  const [imgBroken, setImgBroken] = useState(false)

  const cid = item?.meta?.campaign_id
  const aid = item?.meta?.asset_id

  function load() {
    fetchInboxItem(id)
      .then((found) => {
        setItem(found)
        setLoaded(true)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoaded(true)
      })
    fetchInbox('pending')
      .then((payload) => setQueue(payload.items || []))
      .catch(() => setQueue([]))
  }

  useEffect(load, [brandId, id])

  useEffect(() => {
    setAsset(null)
    setAssetErr('')
    setImgBroken(false)
    if (!cid || !aid) return
    let live = true
    setAssetLoading(true)
    fetchCampaign(cid)
      .then((c) => {
        if (!live) return
        const found = c.assets?.[aid] || null
        setAsset(found)
        if (!found) setAssetErr('That asset is no longer on the campaign.')
      })
      .catch((err: Error) => {
        if (live) setAssetErr(err.message)
      })
      .finally(() => {
        if (live) setAssetLoading(false)
      })
    return () => {
      live = false
    }
  }, [cid, aid])

  const visualUrl = useMemo(() => assetVisualUrl(asset), [asset])
  const caption =
    asset?.caption ||
    asset?.description ||
    item?.meta?.caption ||
    item?.summary ||
    ''
  const visualBrief =
    asset?.visualBrief || asset?.description || asset?.realPhotoBrief || ''

  const rest = useMemo(
    () => queue.filter((row) => row.id !== item?.id).slice(0, 6),
    [queue, item],
  )

  async function act(action: 'approve' | 'reject') {
    if (!item) return
    setBusy(true)
    const result = await inboxAction(item.id, action)
    setBusy(false)
    if (!result.ok) {
      setError(result.error || 'Action failed')
      return
    }
    const next = rest[0]
    navigate(next ? `/review/${encodeURIComponent(next.id)}` : '/review')
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/review" title={item?.title || item?.summary || (loaded ? 'This piece is gone' : 'Opening…')}>
        {item
          ? 'One piece. Approve, send back, or open the studio for this draft only.'
          : loaded
            ? 'It is not in the inbox. Go back and pick another.'
            : 'Loading this piece…'}
      </PageIntro>

      <Tip text="Back to the review inbox.">
        <Link
          to="/review"
          title="Back to the review inbox."
          className="glass-pill inline-flex items-center gap-1.5 rounded-full border border-white/10 px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={2.5} />
          Inbox
        </Link>
      </Tip>

      {error ? <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p> : null}

      {item ? (
        <section className="glass rounded-2xl border-[1.5px] border-ac/35 p-5 shadow-[0_0_0_3px_rgba(52,211,153,.08)] backdrop-blur-xl">
          {assetLoading && !asset ? (
            <div className="mb-4 h-48 animate-pulse rounded-2xl bg-bg3" />
          ) : visualUrl && !imgBroken ? (
            <div className="mb-4">
            <Tip text="Open the full-size image in a new tab." block>
              <a href={visualUrl} target="_blank" rel="noreferrer" className="block">
                <img
                  src={visualUrl}
                  alt={asset?.name || 'Asset visual'}
                  onError={() => setImgBroken(true)}
                  className="max-h-80 w-auto rounded-2xl border border-bd object-contain"
                />
              </a>
            </Tip>
            </div>
          ) : imgBroken ? (
            <div className="mb-4 rounded-2xl border border-bd bg-bg2/50 px-4 py-3 text-sm text-tx3">
              <p>
                ⚠️ Image URL unreachable — <code className="text-xs break-all">{visualUrl}</code>
              </p>
              <p className="mt-1">The file may not be on this server.</p>
              {visualBrief ? <p className="mt-1">Regenerate it in studio.</p> : null}
            </div>
          ) : !cid || !aid || (asset && !visualUrl) ? (
            <div className="mb-4 rounded-2xl border border-dashed border-bd px-4 py-3 text-sm text-tx3">
              <p>No visual on file.</p>
              <p className="mt-1">Open studio for this draft to add or generate one.</p>
            </div>
          ) : null}

          {assetErr ? (
            <p className="mb-3 text-sm text-tx3">
              Could not load the campaign asset ({assetErr}). Caption and the actions below still work.
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="gold">{item.type || 'item'}</Badge>
            {item.sla_state === 'stale' ? <Badge tone="red">Stale</Badge> : null}
            {item.brand_id ? <Badge>{item.brand_id}</Badge> : null}
            {asset?.approvalStatus ? <Badge>{asset.approvalStatus}</Badge> : null}
            {asset?.publishStatus ? <Badge>{asset.publishStatus}</Badge> : null}
          </div>
          <p className="mt-3 text-sm text-tx2">{caption || 'No brief on this card yet.'}</p>
          {visualBrief ? (
            <p className="mt-2 text-sm text-tx3">
              <span className="font-semibold uppercase tracking-wide text-[12px]">Visual brief</span>
              <br />
              {visualBrief}
            </p>
          ) : null}
          <p className="mt-2 text-[12px] font-semibold tracking-wide text-tx3 uppercase">
            Landed {formatStamp(item.created_at)}
            {item.meta?.campaign_id ? ` · ${item.meta.campaign_id}` : ''}
            {item.meta?.asset_id ? ` · ${item.meta.asset_id}` : ''}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Tip text="Mark this approved. It will not go live.">
              <button
                type="button"
                title="Mark this approved. It will not go live."
                disabled={busy}
                onClick={() => act('approve')}
                className="inline-flex items-center gap-2 rounded-full bg-ac px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
              >
                <Check className="h-4 w-4" strokeWidth={2.5} />
                Approve
              </button>
            </Tip>
            <Tip text="Reject this and send it back to studio.">
              <button
                type="button"
                title="Reject this and send it back to studio."
                disabled={busy}
                onClick={() => act('reject')}
                className="inline-flex items-center gap-2 rounded-full border border-bd px-4 py-2 text-sm font-semibold hover:border-red hover:text-red"
              >
                <PressIcon icon={RotateCcw} className="h-4 w-4" />
                Send back
              </button>
            </Tip>
            <Button
              to={studioTo(item)}
              icon={Pencil}
              tone="ghost"
              tip="Open studio with this draft only — not the whole inbox."
            >
              Edit this piece
            </Button>
          </div>
        </section>
      ) : loaded ? (
        <Button to="/create" icon={Sparkles} tip="Open Studio to start a new draft.">
          Go to studio
        </Button>
      ) : null}

      {rest.length ? (
        <section>
          <h2 className="mb-3 font-display text-xl font-semibold">Next in the queue</h2>
          <ul className="space-y-2">
            {rest.map((row) => (
              <QueueItem
                key={row.id}
                to={`/review/${encodeURIComponent(row.id)}`}
                badge={row.type || 'item'}
                tone="gold"
                title={row.title || row.summary || row.id}
                meta={row.brand_id}
                stamp={row.created_at}
                stampKind="created"
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
