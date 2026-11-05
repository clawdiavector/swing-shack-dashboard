import { useState } from 'react'
import { Link } from 'react-router-dom'
import { inboxAction, inboxGoesOutIso, type InboxItem } from '../lib/api'
import { formatStamp } from '../lib/stamp'

const SHOWN = 3
const BRAND: Record<string, string> = { stick: 'Stick', 'swing-shack': 'Swing Shack', 'bag-drop': 'Bag Drop' }

/** Today's short list: the next few drafts, each approvable here. Approving does not post. */
export function NextToApproveView({
  items,
  total,
  busy,
  onApprove,
}: {
  items: InboxItem[]
  total: number
  busy: string
  onApprove: (id: string) => void
}) {
  const shown = items.slice(0, SHOWN)
  return (
    <section className="glass rounded-2xl border border-white/10 p-4" aria-label="Next to approve">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold">Next to approve</h2>
        {total > 0 ? (
          <Link to="/review" className="text-sm font-semibold text-ac hover:underline">
            See all {total}
          </Link>
        ) : null}
      </div>
      {shown.length === 0 ? (
        <p className="mt-2 text-sm text-tx2">Nothing waiting for a yes.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {shown.map((item) => {
            const goesOut = inboxGoesOutIso(item)
            return (
              <li key={item.id} className="flex items-center gap-3">
                <Link to={`/review/${encodeURIComponent(item.id)}`} className="min-w-0 flex-1 hover:text-ac">
                  <span className="block truncate text-sm font-semibold text-tx">{item.title || item.id}</span>
                  <span className="block text-xs text-tx3">
                    {item.brand_id ? `${BRAND[item.brand_id] ?? item.brand_id} · ` : ''}
                    {goesOut ? `Goes out ${formatStamp(goesOut)}` : 'No date yet'}
                  </span>
                </Link>
                <button
                  type="button"
                  title="Mark this approved. It will not go live."
                  disabled={busy === item.id}
                  onClick={() => onApprove(item.id)}
                  className="shrink-0 rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-ac hover:border-ac disabled:opacity-50"
                >
                  Approve
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export function NextToApprove({ items, total, onDone }: { items: InboxItem[]; total: number; onDone: () => void }) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  return (
    <div>
      <NextToApproveView
        items={items}
        total={total}
        busy={busy}
        onApprove={(id) => {
          setBusy(id)
          setError('')
          void inboxAction(id, 'approve').then((r) => {
            setBusy('')
            if (!r.ok) setError(r.error || 'Could not approve it. Nothing was changed.')
            else onDone()
          })
        }}
      />
      {error ? <p className="mt-1 text-xs text-red">{error}</p> : null}
    </div>
  )
}
