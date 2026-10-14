import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EventTypeIcon } from '../../../components/EventTypeIcon'
import { notifyAlertsChanged, onAlertsChanged } from '../../../lib/calendarAlerts'
import { KIND_LABEL, editPlanItem, formatRand } from '../../../lib/plan'
import {
  fetchPlanSteps,
  planStatusLine,
  stepChipLabel,
  stepEditable,
  stepWhen,
  type PlanStep,
} from '../../../lib/planSteps'
import { HoverChip } from './HoverChip'

/** Steps of draft plans due in the month, for the faded chips. They refresh
 *  when a plan changes anywhere on the page. */
export function useMonthPlanSteps(brandId: string, month: string, enabled: boolean) {
  const [steps, setSteps] = useState<PlanStep[]>([])
  const [tick, setTick] = useState(0)

  useEffect(() => onAlertsChanged(() => setTick((t) => t + 1)), [])

  useEffect(() => {
    if (!enabled || !brandId) return
    let cancelled = false
    void fetchPlanSteps(brandId, month).then((s) => {
      if (!cancelled) setSteps(s)
    })
    return () => {
      cancelled = true
    }
  }, [brandId, month, enabled, tick])

  return enabled && brandId ? steps : []
}

/** A faded yellow chip for one step of a draft plan. While the plan is a draft
 *  its date can be moved, or the step removed, right here; everything else is
 *  changed in the Plan list. */
export function PlanStepChip({ s, brandId }: { s: PlanStep; brandId: string }) {
  const [date, setDate] = useState(s.date)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const editable = stepEditable(s)

  async function change(patch: { due: string } | { status: 'removed' }) {
    setBusy(true)
    setError(null)
    const r = await editPlanItem(brandId, s.plan_id, s.item_id, patch)
    setBusy(false)
    if (!r.ok) {
      setError(r.error || 'That did not work.')
      return
    }
    notifyAlertsChanged() // the chips, the alerts and the plan panel all look again
  }

  return (
    <HoverChip
      chipTestId="plan-step-chip"
      cardTestId="plan-step-card"
      cardLabel={`Plan step: ${s.title}`}
      chipClass="flex max-w-full cursor-pointer items-center gap-1 rounded-full border border-dashed border-yel/50 bg-yel/5 px-1.5 py-0.5 text-[10.5px] font-semibold text-yel opacity-70 hover:opacity-100"
      chip={
        <>
          <EventTypeIcon kind={s.event_kind} size="sm" className="!border-0 !bg-transparent !p-0" />
          <span className="min-w-0 truncate">{stepChipLabel(s)}</span>
        </>
      }
    >
      <p className="flex items-center gap-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
        Plan step
        <EventTypeIcon kind={s.event_kind} size="sm" withLabel />
      </p>
      <p className="text-sm font-bold text-tx">{s.title}</p>
      <p className="flex flex-wrap items-center gap-2 text-xs text-tx2">
        <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold tracking-wider uppercase">
          {KIND_LABEL[s.step] || s.step}
        </span>
        {stepWhen(s)}
      </p>
      {s.late ? <p className="text-xs text-red">This date has already passed.</p> : null}
      {s.step === 'boost' ? (
        <p className="text-xs text-tx3">
          {s.budget ? `Planned budget ${formatRand(s.budget)}. Nothing is spent from here.` : 'No budget set yet.'}
        </p>
      ) : null}
      <p className="text-xs text-tx3">{planStatusLine(s)}</p>
      {editable ? (
        <div className="space-y-2 border-t border-bd pt-2" data-testid="plan-step-edit">
          <label className="block text-xs text-tx2">
            Move to
            <input
              type="date"
              aria-label="New date for this step"
              data-testid="plan-step-date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="mt-1 block w-full rounded border border-bd bg-bg px-2 py-1 text-sm text-tx"
            />
          </label>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy || !date || date === s.date}
              onClick={() => void change({ due: date })}
              data-testid="plan-step-move"
              className="rounded-full border border-yel/40 bg-yel/15 px-3 py-1 text-xs font-semibold text-yel hover:bg-yel/25 disabled:opacity-60"
            >
              Move
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void change({ status: 'removed' })}
              data-testid="plan-step-remove"
              className="rounded-full border border-bd px-3 py-1 text-xs font-semibold text-tx2 hover:text-tx disabled:opacity-60"
            >
              Remove step
            </button>
          </div>
          {error ? <p className="text-xs text-red">{error}</p> : null}
        </div>
      ) : (
        <p className="text-xs text-tx3">To change it, reopen the plan in the Plan list.</p>
      )}
      <Link
        to="/calendar/lanes"
        data-testid="plan-step-open"
        className="inline-flex rounded-full border border-yel/40 bg-yel/15 px-3 py-1 text-xs font-semibold text-yel hover:bg-yel/25"
      >
        Open the plan
      </Link>
    </HoverChip>
  )
}
