import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EventTypeIcon } from '../../../components/EventTypeIcon'
import { onAlertsChanged } from '../../../lib/calendarAlerts'
import { KIND_LABEL } from '../../../lib/plan'
import { fetchPlanSteps, planStatusLine, stepChipLabel, stepWhen, type PlanStep } from '../../../lib/planSteps'
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

/** A faded yellow chip for one step of a draft plan. Read-only: the plan itself
 *  is changed in the Plan list. */
export function PlanStepChip({ s }: { s: PlanStep }) {
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
      <p className="text-xs text-tx3">{planStatusLine(s)}</p>
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
