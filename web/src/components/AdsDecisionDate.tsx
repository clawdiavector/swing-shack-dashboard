import { useState } from 'react'
import { call } from './AdsPause'

// Gives an open-ended ad's ad set a decision date (its end date): pick a date, see what
// changes, confirm, then undo if wanted. Nothing is sent to Meta until the confirm button.

type Preview = {
  ad_name?: string
  adset_name?: string
  end_date: string
  note?: string
  ticket: string
}

export type DateState =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'confirm'; preview: Preview }
  | { step: 'set'; actionId: string; endDate: string }
  | { step: 'undone' }
  | { step: 'error'; message: string }

type Handlers = {
  onPreview: () => void
  onConfirm: () => void
  onCancel: () => void
  onUndo: () => void
  onDate: (value: string) => void
}

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'

export function dateInDays(days: number, from: Date = new Date()): string {
  const d = new Date(from.getTime() + days * 86_400_000)
  return d.toISOString().slice(0, 10)
}

export function DateView({
  adName,
  date,
  state,
  handlers,
}: {
  adName: string
  date: string
  state: DateState
  handlers: Handlers
}) {
  switch (state.step) {
    case 'idle':
      return (
        <span className="inline-flex flex-wrap items-center gap-2">
          <input
            type="date"
            value={date}
            onChange={(e) => handlers.onDate(e.target.value)}
            className="rounded-lg border border-white/15 bg-transparent px-2 py-1 text-xs text-tx"
            aria-label="Decision date"
          />
          <button type="button" className={`${btn} text-tx`} onClick={handlers.onPreview}>
            Set decision date
          </button>
        </span>
      )
    case 'busy':
      return <span className="text-xs text-tx3">Working…</span>
    case 'confirm':
      return (
        <div className="w-full rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
          <p className="text-tx">
            Give <span className="font-semibold">{state.preview.adset_name || adName}</span> an end date of{' '}
            <span className="font-semibold">{state.preview.end_date}</span>? {state.preview.note} You can take the date
            off again afterwards.
          </p>
          <div className="mt-2 flex gap-2">
            <button type="button" className={`${btn} bg-yel text-bg`} onClick={handlers.onConfirm}>
              Yes, set it
            </button>
            <button type="button" className={`${btn} text-tx`} onClick={handlers.onCancel}>
              Cancel
            </button>
          </div>
        </div>
      )
    case 'set':
      return (
        <span className="text-xs text-tx2">
          Decision date set for {state.endDate}.{' '}
          <button type="button" className="font-semibold text-ac hover:underline" onClick={handlers.onUndo}>
            Undo
          </button>
        </span>
      )
    case 'undone':
      return <span className="text-xs text-tx2">End date removed.</span>
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

export function SetDecisionDate({ brandId, adId, adName }: { brandId: string; adId: string; adName: string }) {
  const [state, setState] = useState<DateState>({ step: 'idle' })
  const [date, setDate] = useState(() => dateInDays(14))
  const base = `/api/meta/ads/${brandId}`
  const fail = (e: unknown) => setState({ step: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' })

  const handlers: Handlers = {
    onDate: setDate,
    onPreview: () => {
      setState({ step: 'busy' })
      call<{ preview: Preview }>(`${base}/end-date/preview`, { ad_id: adId, end_date: date })
        .then((r) => setState({ step: 'confirm', preview: r.preview }))
        .catch(fail)
    },
    onConfirm: () => {
      if (state.step !== 'confirm') return
      const { ticket, end_date } = state.preview
      setState({ step: 'busy' })
      call<{ action: { id: string } }>(`${base}/end-date`, { ticket })
        .then((r) => setState({ step: 'set', actionId: r.action.id, endDate: end_date }))
        .catch(fail)
    },
    onCancel: () => setState({ step: 'idle' }),
    onUndo: () => {
      if (state.step !== 'set') return
      const id = state.actionId
      setState({ step: 'busy' })
      call(`${base}/actions/${id}/undo`)
        .then(() => setState({ step: 'undone' }))
        .catch(fail)
    },
  }
  return <DateView adName={adName} date={date} state={state} handlers={handlers} />
}
