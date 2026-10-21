import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { rand } from '../lib/rand'
import { call } from './AdsPause'

// Approve a daily-budget change on an ad set: see exactly what changes, approve, and the system makes the change
// in Meta, logs it and offers Undo. POST /api/meta/ads/<brand>/budget-change/preview and /budget-change.
// Nothing is sent to Meta until the approve button.

type Preview = {
  adset_name?: string
  campaign?: string
  before: number
  after: number
  change_pct: number
  per_day: number
  ticket: string
  context?: { month_status?: string; budget?: number | null; mtd_spend?: number | null; guard_on?: boolean }
}

export type ChangeState =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'confirm'; preview: Preview }
  | { step: 'done'; actionId: string; before: number; after: number }
  | { step: 'undone' }
  | { step: 'error'; message: string }

type Handlers = { onPreview: () => void; onConfirm: () => void; onCancel: () => void; onUndo: () => void }

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'

export function ChangeView({ label, state, handlers }: { label: string; state: ChangeState; handlers: Handlers }) {
  switch (state.step) {
    case 'idle':
      return (
        <button type="button" className={`${btn} text-tx`} onClick={handlers.onPreview}>
          {label}
        </button>
      )
    case 'busy':
      return <span className="text-xs text-tx3">Working…</span>
    case 'confirm': {
      const p = state.preview
      const over = p.context?.month_status === 'OVER' || p.context?.month_status === 'AT_RISK'
      return (
        <div className="w-full rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
          <p className="text-tx">
            Change the daily budget of <span className="font-semibold">{p.adset_name}</span>
            {p.campaign ? <span className="text-tx3"> ({p.campaign})</span> : null} from{' '}
            <span className="font-semibold">{rand(p.before)}</span> to <span className="font-semibold">{rand(p.after)}</span> a day (
            {p.change_pct > 0 ? '+' : ''}
            {p.change_pct}%, {p.per_day > 0 ? '+' : ''}
            {rand(p.per_day)} a day)?
          </p>
          {over && p.after > p.before ? (
            <p className="mt-1 font-semibold text-red">
              This brand is already {p.context?.month_status === 'OVER' ? 'over' : 'heading over'} its monthly budget
              {p.context?.budget ? ` of ${rand(p.context.budget)}` : ''}.{' '}
              {p.context?.guard_on ? 'The budget guard will pause this ad set again at its next hourly check.' : 'Raising this adds to that.'}
            </p>
          ) : null}
          <p className="mt-1 text-xs text-tx3">Made in Meta straight away, logged, and you can put it back afterwards.</p>
          <div className="mt-2 flex gap-2">
            <button type="button" className={`${btn} bg-yel text-bg`} onClick={handlers.onConfirm}>
              Approve change
            </button>
            <button type="button" className={`${btn} text-tx`} onClick={handlers.onCancel}>
              Cancel
            </button>
          </div>
        </div>
      )
    }
    case 'done':
      return (
        <span className="text-xs text-tx2">
          Budget changed from {rand(state.before)} to {rand(state.after)} a day.{' '}
          <button type="button" className="font-semibold text-ac hover:underline" onClick={handlers.onUndo}>
            Undo
          </button>
        </span>
      )
    case 'undone':
      return <span className="text-xs text-tx2">Budget put back.</span>
    case 'error':
      return (
        <span className="text-xs text-red">
          {state.message}{' '}
          <button type="button" className="font-semibold underline" onClick={handlers.onCancel}>
            OK
          </button>
        </span>
      )
  }
}

export function ChangeBudget({
  brandId,
  label,
  target,
}: {
  brandId: string
  label: string
  target: { ad_id?: string; adset_id?: string; pct: number }
}) {
  const [state, setState] = useState<ChangeState>({ step: 'idle' })
  const base = `/api/meta/ads/${brandId}`
  const fail = (e: unknown) => setState({ step: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' })
  const handlers: Handlers = {
    onPreview: () => {
      setState({ step: 'busy' })
      call<{ preview: Preview }>(`${base}/budget-change/preview`, target)
        .then((r) => setState({ step: 'confirm', preview: r.preview }))
        .catch(fail)
    },
    onConfirm: () => {
      if (state.step !== 'confirm') return
      const { ticket, before, after } = state.preview
      setState({ step: 'busy' })
      call<{ action: { id: string } }>(`${base}/budget-change`, { ticket })
        .then((r) => setState({ step: 'done', actionId: r.action.id, before, after }))
        .catch(fail)
    },
    onCancel: () => setState({ step: 'idle' }),
    onUndo: () => {
      if (state.step !== 'done') return
      const id = state.actionId
      setState({ step: 'busy' })
      call(`${base}/actions/${id}/undo`)
        .then(() => setState({ step: 'undone' }))
        .catch(fail)
    },
  }
  return <ChangeView label={label} state={state} handlers={handlers} />
}

type SetRow = { id: string; name?: string; kind: string; amount: number; level?: string; objective?: string | null }

const LEADISH = new Set(['OUTCOME_LEADS', 'OUTCOME_ENGAGEMENT', 'OUTCOME_SALES'])

/** The set of running ad sets with a change that moves money from traffic and awareness towards leads and chats. */
export function moveSuggestions(sets: SetRow[]): { row: SetRow; pct: number; label: string }[] {
  return sets
    .filter((s) => s.level === 'adset' && s.kind === 'daily')
    .map((row) =>
      LEADISH.has(row.objective ?? '')
        ? { row, pct: 0.2, label: 'Raise by 20%' }
        : { row, pct: -0.5, label: 'Lower by half' },
    )
}

export function MoveBudget({ brandId }: { brandId: string }) {
  const [sets, setSets] = useState<SetRow[] | null>(null)
  useEffect(() => {
    setSets(null)
    getJson<{ budget?: { sets?: SetRow[] } | null }>(`/api/meta/ads/${brandId}/budget`)
      .then((r) => setSets(r.budget?.sets ?? []))
      .catch(() => setSets([]))
  }, [brandId])
  return <MoveBudgetView brandId={brandId} sets={sets} />
}

export function MoveBudgetView({ brandId, sets }: { brandId: string; sets: SetRow[] | null }) {
  if (!sets) return <p className="mt-2 text-xs text-tx3">Loading ad sets…</p>
  const rows = moveSuggestions(sets)
  if (!rows.length) return <p className="mt-2 text-xs text-tx3">No running ad set has a daily budget of its own to move.</p>
  return (
    <ul className="mt-2 space-y-2">
      {rows.map(({ row, pct, label }) => (
        <li key={row.id} className="flex flex-wrap items-center gap-2 text-xs text-tx2">
          <span>
            {row.name} <span className="text-tx3">({rand(row.amount)} a day)</span>
          </span>
          <ChangeBudget brandId={brandId} label={label} target={{ adset_id: row.id, pct }} />
        </li>
      ))}
    </ul>
  )
}
