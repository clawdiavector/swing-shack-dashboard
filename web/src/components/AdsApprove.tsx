import { useState, type ReactNode } from 'react'
import { call } from './AdsPause'

// One approve flow for any change the system makes in Meta: a button, a preview that says exactly what changes,
// Approve, then the system makes the change, logs it and offers Undo. Nothing is sent to Meta until Approve.

export type ApproveState<P> =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'confirm'; preview: P }
  | { step: 'done'; actionId: string; preview: P }
  | { step: 'undone' }
  | { step: 'error'; message: string }

type Handlers = { onPreview: () => void; onConfirm: () => void; onCancel: () => void; onUndo: () => void }

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'

export function ApproveView<P>({
  label,
  state,
  handlers,
  describe,
  doneText,
  warning,
}: {
  label: string
  state: ApproveState<P>
  handlers: Handlers
  describe: (p: P) => ReactNode
  doneText: (p: P) => string
  warning?: (p: P) => string | undefined
}) {
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
      const w = warning?.(state.preview)
      return (
        <div className="w-full rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
          <div className="text-tx">{describe(state.preview)}</div>
          {w ? <p className="mt-1 text-xs font-semibold text-red">{w}</p> : null}
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
          {doneText(state.preview)}{' '}
          <button type="button" className="font-semibold text-ac hover:underline" onClick={handlers.onUndo}>
            Undo
          </button>
        </span>
      )
    case 'undone':
      return <span className="text-xs text-tx2">Put back.</span>
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

export function Approve<P extends { ticket: string }>({
  brandId,
  label,
  previewPath,
  applyPath,
  body,
  describe,
  doneText,
  warning,
}: {
  brandId: string
  label: string
  previewPath: string
  applyPath: string
  body: object
  describe: (p: P) => ReactNode
  doneText: (p: P) => string
  warning?: (p: P) => string | undefined
}) {
  const [state, setState] = useState<ApproveState<P>>({ step: 'idle' })
  const base = `/api/meta/ads/${brandId}`
  const fail = (e: unknown) => setState({ step: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' })
  const handlers: Handlers = {
    onPreview: () => {
      setState({ step: 'busy' })
      call<{ preview: P }>(`${base}/${previewPath}`, body)
        .then((r) => setState({ step: 'confirm', preview: r.preview }))
        .catch(fail)
    },
    onConfirm: () => {
      if (state.step !== 'confirm') return
      const preview = state.preview
      setState({ step: 'busy' })
      call<{ action: { id: string } }>(`${base}/${applyPath}`, { ticket: preview.ticket })
        .then((r) => setState({ step: 'done', actionId: r.action.id, preview }))
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
  return (
    <ApproveView label={label} state={state} handlers={handlers} describe={describe} doneText={doneText} warning={warning} />
  )
}
