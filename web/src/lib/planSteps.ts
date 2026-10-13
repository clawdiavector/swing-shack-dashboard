// Steps of draft plans, drawn faded on the month grid until the plan is put on
// the calendar.

import { KIND_LABEL, formatDay, type PlanItemKind } from './plan'

export type PlanStep = {
  key: string
  plan_id: string
  item_id: string
  title: string
  step: PlanItemKind
  date: string
  late: boolean
  channel: string
  event_name: string
  event_date: string
  event_kind: string
  plan_status: 'proposed' | 'approved'
}

export async function fetchPlanSteps(brand: string, month: string): Promise<PlanStep[]> {
  try {
    const res = await fetch(`/api/plan/v1/${encodeURIComponent(brand)}/month?month=${encodeURIComponent(month)}`, {
      credentials: 'same-origin',
    })
    if (!res.ok) return []
    const j = (await res.json()) as { ok?: boolean; steps?: PlanStep[] }
    return j.ok ? j.steps || [] : []
  } catch {
    return []
  }
}

/** Steps grouped by the day they are due. */
export function stepsByDay(steps: PlanStep[]): Record<string, PlanStep[]> {
  const out: Record<string, PlanStep[]> = {}
  for (const s of steps) (out[s.date] ||= []).push(s)
  return out
}

/** The short label on the chip: the kind of step, then the date it is for. */
export function stepChipLabel(s: PlanStep): string {
  return `${KIND_LABEL[s.step] || s.step} · ${s.event_name}`
}

/** What the card says about where the plan has got to. */
export function planStatusLine(s: PlanStep): string {
  return s.plan_status === 'approved'
    ? 'Plan approved, not on the calendar yet.'
    : 'Draft plan. Nothing is scheduled.'
}

export function stepWhen(s: PlanStep): string {
  return `${formatDay(s.date)} · for ${s.event_name} on ${formatDay(s.event_date)}`
}
