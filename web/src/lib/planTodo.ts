// The to-do list: every step still to do across the live plans, by date.

import { KIND_LABEL, type PlanItemKind } from './plan'

export type TodoBucket = 'overdue' | 'today' | 'this_week' | 'later'

export const BUCKETS: TodoBucket[] = ['overdue', 'today', 'this_week', 'later']

export const BUCKET_LABEL: Record<TodoBucket, string> = {
  overdue: 'Overdue',
  today: 'Today',
  this_week: 'This week',
  later: 'Coming up',
}

export type TodoStep = {
  key: string
  brand_id: string
  plan_id: string
  item_id: string
  step: PlanItemKind
  title: string
  due: string
  days: number
  bucket: TodoBucket
  event_name: string
  event_date: string
  event_kind: string
  plan_status: string
  asked?: { to: string; at: string } | null
  /** What the step still needs: "no shot list yet", "nobody asked yet", "no budget yet". */
  needs: string[]
}

export type TodoResult = {
  ok: boolean
  error?: string
  steps: TodoStep[]
  counts: Record<TodoBucket, number>
}

const EMPTY: Record<TodoBucket, number> = { overdue: 0, today: 0, this_week: 0, later: 0 }

export async function fetchTodo(brand: string): Promise<TodoResult> {
  try {
    const res = await fetch(`/api/plan-todo?brand=${encodeURIComponent(brand || 'all')}`, { credentials: 'same-origin' })
    if (res.status === 401) return { ok: false, error: 'Please sign in again.', steps: [], counts: EMPTY }
    const j = (await res.json().catch(() => ({}))) as Partial<TodoResult>
    if (!res.ok || j.ok === false) {
      return { ok: false, error: j.error || `Something went wrong (${res.status}).`, steps: [], counts: EMPTY }
    }
    return { ok: true, steps: j.steps || [], counts: { ...EMPTY, ...(j.counts || {}) } }
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.', steps: [], counts: EMPTY }
  }
}

/** Steps grouped by bucket, every bucket present and in order. */
export function groupTodo(steps: TodoStep[]): Record<TodoBucket, TodoStep[]> {
  const out: Record<TodoBucket, TodoStep[]> = { overdue: [], today: [], this_week: [], later: [] }
  for (const s of steps) out[s.bucket]?.push(s)
  return out
}

/** "3 days ago", "today", "tomorrow", "in 5 days". */
export function dueWords(days: number): string {
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  return days > 0 ? `in ${days} days` : `${-days} days ago`
}

/** The one-line heading for the page. */
export function todoSummary(counts: Record<TodoBucket, number>): string {
  const parts: string[] = []
  if (counts.overdue) parts.push(`${counts.overdue} overdue`)
  if (counts.today) parts.push(`${counts.today} due today`)
  if (counts.this_week) parts.push(`${counts.this_week} more this week`)
  return parts.length ? parts.join(', ') + '.' : 'Nothing is overdue or due today.'
}

export function stepLabel(s: TodoStep): string {
  return KIND_LABEL[s.step] || s.step
}
