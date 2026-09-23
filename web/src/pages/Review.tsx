import { Check, Inbox, RotateCcw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, Button, PressIcon, QueueItem, StatCard, Tip } from '../components/ui'
import { fetchInbox, inboxAction, type InboxItem } from '../lib/api'
import { formatStamp } from '../lib/stamp'

function itemType(item: InboxItem) {
  return (item.type || 'item').toLowerCase()
}

export function Review() {
  const { brandId } = useBrand()
  const [items, setItems] = useState<InboxItem[]>([])
  const [pending, setPending] = useState<number | null>(null)
  const [stale, setStale] = useState<number | null>(null)
  const [approved, setApproved] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filter, setFilter] = useState('all')

  function load() {
    fetchInbox('pending', brandId)
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
    return ['all', ...Array.from(set).sort()]
  }, [items])

  const shown = filter === 'all' ? items : items.filter((item) => itemType(item) === filter)
  const first = shown[0]

  return (
    <div className="space-y-6">
      <PageIntro here="/review" title="Waiting on you">
        Open one piece. Approve here, or edit that draft in studio — not the whole wall.
      </PageIntro>

      {error ? <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p> : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={Inbox} label="Pending" value={pending ?? '—'} hint="On your desk now" tone="gold" />
        <StatCard icon={RotateCcw} label="Stale" value={stale ?? '—'} hint="Sitting too long" tone="mute" />
        <StatCard icon={Check} label="Cleared today" value={approved ?? '—'} hint="Approved, not live" tone="green" />
      </div>

      <FilterChips
        value={filter}
        onChange={setFilter}
        options={types.map((id) => ({ id, label: id === 'all' ? 'All' : id }))}
      />

      {first ? (
        <section className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl border-[1.5px] border-ac/35 px-4 py-3 backdrop-blur-xl">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold tracking-wide text-tx3 uppercase">Next up</p>
            <p className="font-display text-lg font-semibold leading-snug">{first.title || first.summary}</p>
            <p className="text-xs text-tx3">
              {first.type || 'item'} · {first.brand_id || 'brand'} · {formatStamp(first.created_at)}
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
          {shown.map((item) => (
            <QueueItem
              key={item.id}
              to={`/review/${encodeURIComponent(item.id)}`}
              badge={item.sla_state === 'stale' ? 'stale' : item.type || 'item'}
              tone={item.sla_state === 'stale' ? 'gold' : 'gold'}
              title={item.title || item.summary || item.id}
              meta={item.brand_id}
              stamp={item.created_at}
              stampKind="created"
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
          ))}
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
