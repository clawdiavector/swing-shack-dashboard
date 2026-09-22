import { ArrowLeft, Check, Pencil, RotateCcw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge, Button, PressIcon, QueueItem, Tip } from '../components/ui'
import { fetchInbox, fetchInboxItem, inboxAction, type InboxItem } from '../lib/api'
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
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="gold">{item.type || 'item'}</Badge>
            {item.sla_state === 'stale' ? <Badge tone="red">Stale</Badge> : null}
            {item.brand_id ? <Badge>{item.brand_id}</Badge> : null}
          </div>
          <p className="mt-3 text-sm text-tx2">{item.summary || 'No brief on this card yet.'}</p>
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
