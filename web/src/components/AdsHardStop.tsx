import { useState } from 'react'
import { call } from './AdsPause'
import { rand } from '../lib/rand'
import type { BudgetEval } from './AdsBudget'

// Hard stop: Meta's own account spending limit, kept at (spend at the start of the month + the monthly budget).
// When it is reached Meta stops every ad in the brand's account. POST /api/meta/ads/<brand>/hard-stop.
// Turning it on first shows exactly what it would do; nothing is sent to Meta until the confirm button.

export type HardStopInfo = {
  on: boolean
  cap?: number | null
  amount_spent?: number | null
  writes_enabled?: boolean
  plan?: { action: string; reason?: string; cap?: number; stops_now?: boolean; room?: number } | null
}

type Preview = {
  plan: { action: string; reason?: string; cap?: number; stops_now?: boolean; room?: number }
  budget: number
  mtd_spend: number
  amount_spent: number
  current_cap: number
}

export type HardState =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'confirm'; preview: Preview }
  | { step: 'error'; message: string }

type Handlers = { onPreview: () => void; onConfirm: () => void; onCancel: () => void; onOff: () => void }

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'
const cents = (n: number | null | undefined) => (n == null ? null : n / 100)

export function HardStopView({
  info,
  budget,
  state,
  handlers,
}: {
  info: HardStopInfo
  budget: BudgetEval | null
  state: HardState
  handlers: Handlers
}) {
  const cap = cents(info.cap)
  return (
    <div className="space-y-2 rounded-xl border border-white/10 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-tx">Hard stop in Meta</span>
        <span className={`text-xs font-semibold ${info.on ? 'text-ac' : 'text-tx3'}`}>{info.on ? 'ON' : 'OFF'}</span>
      </div>
      <p className="text-xs text-tx2">
        {info.on
          ? `Meta stops every ad in this account once its spending limit of ${rand(cap)} is reached. The limit follows the monthly budget and is lifted for the new month on the 1st.`
          : 'Off: the budget only warns. Turn it on and Meta itself stops every ad in this brand’s ad account when the month’s budget is used up.'}
      </p>
      {state.step === 'idle' ? (
        info.on ? (
          <button type="button" className={`${btn} text-tx`} onClick={handlers.onOff}>
            Turn hard stop off
          </button>
        ) : (
          <button
            type="button"
            className={`${btn} text-tx disabled:opacity-50`}
            disabled={!budget?.budget}
            title={budget?.budget ? undefined : 'Set a monthly budget first'}
            onClick={handlers.onPreview}
          >
            Turn hard stop on…
          </button>
        )
      ) : null}
      {state.step === 'busy' ? <span className="text-xs text-tx3">Working…</span> : null}
      {state.step === 'confirm' ? (
        <div className="rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
          {state.preview.plan.action === 'blocked' ? (
            <p className="text-tx">{state.preview.plan.reason}</p>
          ) : (
            <>
              <p className="text-tx">
                Budget {rand(state.preview.budget)}, spent this month {rand(state.preview.mtd_spend)}. Campaign OS would
                set the account&apos;s spending limit to <span className="font-semibold">{rand(cents(state.preview.plan.cap))}</span>{' '}
                (lifetime spend now {rand(cents(state.preview.amount_spent))}).
              </p>
              {state.preview.plan.stops_now ? (
                <p className="mt-1 font-semibold text-red">
                  The budget is already used up, so every ad in this account would stop delivering right away, and stay
                  stopped until the 1st of next month or until you change the budget.
                </p>
              ) : (
                <p className="mt-1 text-tx2">Ads keep running until {rand(cents(state.preview.plan.room))} more has been spent.</p>
              )}
              <p className="mt-1 text-xs text-tx3">
                Meta can go a little past a limit before it catches up. Turning this off puts back the limit the account
                had before (none).
              </p>
            </>
          )}
          <div className="mt-2 flex gap-2">
            {state.preview.plan.action !== 'blocked' ? (
              <button type="button" className={`${btn} bg-yel text-bg`} onClick={handlers.onConfirm}>
                Yes, turn it on
              </button>
            ) : null}
            <button type="button" className={`${btn} text-tx`} onClick={handlers.onCancel}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {state.step === 'error' ? (
        <span className="text-xs text-red">
          {state.message}{' '}
          <button type="button" className="font-semibold underline" onClick={handlers.onCancel}>
            OK
          </button>
        </span>
      ) : null}
      {info.writes_enabled === false ? <p className="text-xs text-tx3">One-click ad changes are switched off, so this cannot be turned on.</p> : null}
    </div>
  )
}

export function HardStop({
  brandId,
  info,
  budget,
  onChange,
}: {
  brandId: string
  info: HardStopInfo
  budget: BudgetEval | null
  onChange: () => void
}) {
  const [state, setState] = useState<HardState>({ step: 'idle' })
  const path = `/api/meta/ads/${brandId}/hard-stop`
  const fail = (e: unknown) => setState({ step: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' })
  const handlers: Handlers = {
    onPreview: () => {
      setState({ step: 'busy' })
      call<{ preview: Preview }>(path, { on: true })
        .then((r) => setState({ step: 'confirm', preview: r.preview }))
        .catch(fail)
    },
    onConfirm: () => {
      setState({ step: 'busy' })
      call(path, { on: true, confirm: true })
        .then(() => {
          setState({ step: 'idle' })
          onChange()
        })
        .catch(fail)
    },
    onCancel: () => setState({ step: 'idle' }),
    onOff: () => {
      setState({ step: 'busy' })
      call(path, { on: false })
        .then(() => {
          setState({ step: 'idle' })
          onChange()
        })
        .catch(fail)
    },
  }
  return <HardStopView info={info} budget={budget} state={state} handlers={handlers} />
}
