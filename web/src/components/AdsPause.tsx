import { useState } from 'react'

// One-click pause for a single ad: preview, confirm, then undo. The server does the
// checking (POST /api/meta/ads/<brand>/pause/preview, /pause, /actions/<id>/undo).
// Nothing is sent to Meta until the person presses the confirm button.

type Preview = { ad_id: string; ad_name?: string; status_now: string; will_set: string; ticket: string }

export type PauseState =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'confirm'; preview: Preview }
  | { step: 'paused'; actionId: string }
  | { step: 'undone' }
  | { step: 'error'; message: string }

type Handlers = { onPreview: () => void; onConfirm: () => void; onCancel: () => void; onUndo: () => void }

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'

export function PauseView({ adName, state, handlers }: { adName: string; state: PauseState; handlers: Handlers }) {
  switch (state.step) {
    case 'idle':
      return (
        <button type="button" className={`${btn} text-tx`} onClick={handlers.onPreview}>
          Pause this ad
        </button>
      )
    case 'busy':
      return <span className="text-xs text-tx3">Working…</span>
    case 'confirm':
      return (
        <div className="w-full rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
          <p className="text-tx">
            Pause <span className="font-semibold">{state.preview.ad_name || adName}</span> in Meta? It is{' '}
            {state.preview.status_now.toLowerCase()} now and will stop delivering. You can undo it afterwards.
          </p>
          <div className="mt-2 flex gap-2">
            <button type="button" className={`${btn} bg-yel text-bg`} onClick={handlers.onConfirm}>
              Yes, pause it
            </button>
            <button type="button" className={`${btn} text-tx`} onClick={handlers.onCancel}>
              Cancel
            </button>
          </div>
        </div>
      )
    case 'paused':
      return (
        <span className="text-xs text-tx2">
          Paused in Meta.{' '}
          <button type="button" className="font-semibold text-ac hover:underline" onClick={handlers.onUndo}>
            Undo
          </button>
        </span>
      )
    case 'undone':
      return <span className="text-xs text-tx2">Back to running.</span>
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

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const json = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string } & T
  if (!res.ok || json.ok === false) throw new Error(json.error || `Meta change failed (${res.status})`)
  return json
}

export function PauseAd({ brandId, adId, adName }: { brandId: string; adId: string; adName: string }) {
  const [state, setState] = useState<PauseState>({ step: 'idle' })
  const base = `/api/meta/ads/${brandId}`
  const fail = (e: unknown) => setState({ step: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' })

  const handlers: Handlers = {
    onPreview: () => {
      setState({ step: 'busy' })
      call<{ preview: Preview }>(`${base}/pause/preview`, { ad_id: adId })
        .then((r) => setState({ step: 'confirm', preview: r.preview }))
        .catch(fail)
    },
    onConfirm: () => {
      if (state.step !== 'confirm') return
      const ticket = state.preview.ticket
      setState({ step: 'busy' })
      call<{ action: { id: string } }>(`${base}/pause`, { ticket })
        .then((r) => setState({ step: 'paused', actionId: r.action.id }))
        .catch(fail)
    },
    onCancel: () => setState({ step: 'idle' }),
    onUndo: () => {
      if (state.step !== 'paused') return
      const id = state.actionId
      setState({ step: 'busy' })
      call(`${base}/actions/${id}/undo`)
        .then(() => setState({ step: 'undone' }))
        .catch(fail)
    },
  }
  return <PauseView adName={adName} state={state} handlers={handlers} />
}
