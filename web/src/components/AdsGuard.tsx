import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { rand } from '../lib/rand'
import { call } from './AdsPause'

// Budget guard: when a brand's monthly budget is used up, an hourly check pauses its running ad sets.
// Off until a person turns it on. GET/POST /api/meta/ads/<brand>/guard; each pause is listed here with a way back.

type Target = { id: string; name?: string | null; campaign?: string | null }
type Plan = { trigger: boolean; reason: string; targets: Target[]; running: number; enabled?: boolean }
type Paused = { id: string; ad_id: string; ad_name?: string | null; at: string; kind: string; note?: string }

export type GuardInfo = {
  auto_pause: boolean
  budget?: number | null
  period?: 'week' | 'month'
  writes_enabled?: boolean
  last?: { at?: string; plan?: Plan; paused?: Paused[]; errors?: unknown[] } | null
  paused: Paused[]
}

type Preview = { plan: Plan; budget: number; mtd_spend: number }

export type GuardState =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'confirm'; preview: Preview }
  | { step: 'error'; message: string }

type Handlers = {
  onPreview: () => void
  onConfirm: () => void
  onCancel: () => void
  onOff: () => void
  onUndo: (id: string) => void
}

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'

export function GuardView({
  info,
  hasBudget,
  state,
  handlers,
}: {
  info: GuardInfo
  hasBudget: boolean
  state: GuardState
  handlers: Handlers
}) {
  const last = info.last
  const w = info.period === 'week' ? 'week' : 'month'
  return (
    <div className="space-y-2 rounded-xl border border-white/10 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-tx">Hard stop: pause the ads at the budget</span>
        <span className={`text-xs font-semibold ${info.auto_pause ? 'text-ac' : 'text-tx3'}`}>{info.auto_pause ? 'ON' : 'OFF'}</span>
      </div>
      <p className="text-xs text-tx2">
        {info.auto_pause
          ? `Every hour this checks the ${w}’s spend. When the budget is used up, it pauses this brand’s running ad sets. It never turns anything back on; a new ${w} gives the budget back, and you turn ad sets on yourself.`
          : `Off: the budget only warns. Turn it on and an hourly check pauses this brand’s running ad sets when the ${w}’s budget is used up.`}
      </p>
      {last?.plan ? (
        <p className="text-xs text-tx3">
          Last check{last.at ? ` ${last.at.slice(0, 16).replace('T', ' ')} UTC` : ''}: {last.plan.reason}
          {!info.auto_pause && last.plan.trigger
            ? ` With the guard on it would pause ${last.plan.targets.length} ad set${last.plan.targets.length === 1 ? '' : 's'}.`
            : ''}
        </p>
      ) : (
        <p className="text-xs text-tx3">No check has run yet. The first one runs within the hour.</p>
      )}
      {state.step === 'idle' ? (
        info.auto_pause ? (
          <button type="button" className={`${btn} text-tx`} onClick={handlers.onOff}>
            Turn budget guard off
          </button>
        ) : (
          <button
            type="button"
            className={`${btn} text-tx disabled:opacity-50`}
            disabled={!hasBudget}
            title={hasBudget ? undefined : 'Set a budget first'}
            onClick={handlers.onPreview}
          >
            Turn budget guard on…
          </button>
        )
      ) : null}
      {state.step === 'busy' ? <span className="text-xs text-tx3">Working…</span> : null}
      {state.step === 'confirm' ? (
        <div className="rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
          <p className="text-tx">
            Budget {rand(state.preview.budget)}, spent this {w} {rand(state.preview.mtd_spend)}. {state.preview.plan.reason}
          </p>
          {state.preview.plan.trigger ? (
            <>
              <p className="mt-1 font-semibold text-red">
                Turned on now, the next hourly check would pause {state.preview.plan.targets.length} ad set
                {state.preview.plan.targets.length === 1 ? '' : 's'}:
              </p>
              <ul className="mt-1 list-disc pl-5 text-xs text-tx2">
                {state.preview.plan.targets.map((t) => (
                  <li key={t.id}>
                    {t.name} <span className="text-tx3">({t.campaign})</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-1 text-tx2">Nothing would be paused now.</p>
          )}
          <p className="mt-1 text-xs text-tx3">Each pause is logged and can be turned back on from here.</p>
          <div className="mt-2 flex gap-2">
            <button type="button" className={`${btn} bg-yel text-bg`} onClick={handlers.onConfirm}>
              Yes, turn it on
            </button>
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
      {info.paused.length ? (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-tx">Paused by the guard</p>
          <ul className="space-y-1 text-xs text-tx2">
            {info.paused.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2">
                <span>
                  {p.ad_name ?? p.ad_id}
                  <span className="text-tx3"> · {p.at.slice(0, 16).replace('T', ' ')} UTC</span>
                </span>
                <button type="button" className="font-semibold text-ac hover:underline" onClick={() => handlers.onUndo(p.id)}>
                  Turn back on
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {info.writes_enabled === false ? (
        <p className="text-xs text-tx3">One-click ad changes are switched off, so the guard can only record what it would do.</p>
      ) : null}
    </div>
  )
}

export function BudgetGuard({ brandId, hasBudget }: { brandId: string; hasBudget: boolean }) {
  const [info, setInfo] = useState<GuardInfo>({ auto_pause: false, paused: [] })
  const [state, setState] = useState<GuardState>({ step: 'idle' })
  const path = `/api/meta/ads/${brandId}/guard`
  const load = () =>
    getJson<GuardInfo>(path)
      .then(setInfo)
      .catch(() => undefined)
  useEffect(() => {
    setState({ step: 'idle' })
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brandId])

  const fail = (e: unknown) => setState({ step: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' })
  const done = () => {
    setState({ step: 'idle' })
    void load()
  }
  const handlers: Handlers = {
    onPreview: () => {
      setState({ step: 'busy' })
      call<{ preview: Preview }>(path, { on: true })
        .then((r) => setState({ step: 'confirm', preview: r.preview }))
        .catch(fail)
    },
    onConfirm: () => {
      setState({ step: 'busy' })
      call(path, { on: true, confirm: true }).then(done).catch(fail)
    },
    onCancel: () => setState({ step: 'idle' }),
    onOff: () => {
      setState({ step: 'busy' })
      call(path, { on: false }).then(done).catch(fail)
    },
    onUndo: (id) => {
      setState({ step: 'busy' })
      call(`/api/meta/ads/${brandId}/actions/${id}/undo`).then(done).catch(fail)
    },
  }
  return <GuardView info={info} hasBudget={hasBudget} state={state} handlers={handlers} />
}
