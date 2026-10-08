import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchPlanningWaiting } from '../../../lib/api'
import type { PlanningWaiting, PlanningWaitingSuggestion } from '../../../lib/planningTypes'
import { formatPlanDate } from './PlanList'

const TYPE_LABEL: Record<string, string> = {
  campaign: 'Campaign',
  moment: 'Moment',
  content: 'Content',
  reminder: 'Reminder',
}

// "stick-retail" / "ss-membership" → "Retail" / "Membership"
function pillarLabel(id: string): string {
  const word = id.split('-').pop() || id
  return word.charAt(0).toUpperCase() + word.slice(1)
}

/**
 * What the operator suggested and has not added to the calendar yet, each
 * with its button. Sits at the top of Plan so a new suggestion never has to
 * be found through Search Dates.
 */
export function WaitingForYou({
  brandId,
  refreshKey,
  onApprove,
  onOpenDetails,
}: {
  brandId: string
  refreshKey: number
  onApprove: (candidateId: string) => Promise<{ ok: boolean; error?: string }>
  onOpenDetails: (candidateId: string) => void
}) {
  const [items, setItems] = useState<PlanningWaitingSuggestion[] | null>(null)
  const [addingId, setAddingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!brandId) return
    let gone = false
    fetchPlanningWaiting(brandId)
      .then((j) => {
        if (!gone) setItems((j as PlanningWaiting).suggestions || [])
      })
      .catch(() => {
        if (!gone) setItems([])
      })
    return () => {
      gone = true
    }
  }, [brandId, refreshKey])

  if (!items) return null
  if (!items.length) {
    return (
      <p className="text-sm text-tx3" data-testid="waiting-empty">
        Nothing waiting for you. Dates and campaigns you suggest will show here first.
      </p>
    )
  }

  return (
    <section
      className="space-y-2 rounded-2xl border-[1.5px] border-yel/40 bg-yel/5 p-4"
      data-testid="waiting-for-you"
    >
      <h2 className="font-display text-lg font-semibold">
        Waiting for you <span className="text-tx3">· {items.length}</span>
      </h2>
      <p className="text-xs text-tx3">
        You suggested {items.length === 1 ? 'this' : 'these'}. Nothing is on the calendar until you
        add it.
      </p>
      {error ? <p className="text-xs text-red">{error}</p> : null}
      <ul className="space-y-1">
        {items.map((s) => {
          const adding = addingId === s.candidate_id
          const pillars = (s.pillars || []).map(pillarLabel).join(', ')
          return (
            <li
              key={s.candidate_id}
              className="flex flex-wrap items-center gap-3 rounded-md bg-bg2 px-3 py-2"
              data-testid="waiting-row"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-tx">{s.title}</p>
                <p className="mt-0.5 text-xs text-tx3">
                  {s.date ? formatPlanDate(s.date) : 'No date yet'}
                  {s.end_date && s.end_date !== s.date ? ` – ${formatPlanDate(s.end_date)}` : ''}
                  {' · '}
                  {TYPE_LABEL[s.type || ''] || 'Moment'}
                  {pillars ? ` · ${pillars}` : ''}
                </p>
                {s.why_it_matters ? (
                  <p className="mt-0.5 truncate text-xs text-tx2">{s.why_it_matters}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => onOpenDetails(s.candidate_id)}
                className="shrink-0 rounded-full border border-white/10 px-3 py-1.5 text-xs font-semibold text-tx2 hover:border-yel/60 hover:text-yel"
              >
                Details
              </button>
              <button
                type="button"
                disabled={adding}
                data-testid="waiting-add"
                onClick={async () => {
                  setAddingId(s.candidate_id)
                  setError(null)
                  try {
                    const r = await onApprove(s.candidate_id)
                    if (!r.ok) setError(r.error || `Could not add "${s.title}" to the calendar.`)
                  } finally {
                    setAddingId(null)
                  }
                }}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg hover:bg-yel/90 disabled:opacity-60"
              >
                {adding ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                {adding ? 'Adding…' : 'Add to calendar'}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
