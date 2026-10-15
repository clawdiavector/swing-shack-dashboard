import { CheckCircle2, ListChecks, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useBrand, useBrandScope } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { EventTypeIcon } from '../components/EventTypeIcon'
import { notifyAlertsChanged, onAlertsChanged } from '../lib/calendarAlerts'
import { editPlanItem, formatDay } from '../lib/plan'
import {
  BUCKETS,
  BUCKET_LABEL,
  dueWords,
  fetchTodo,
  groupTodo,
  stepLabel,
  todoSummary,
  type TodoResult,
  type TodoStep,
} from '../lib/planTodo'

const BRAND: Record<string, string> = { stick: 'Stick', 'swing-shack': 'Swing Shack', 'bag-drop': 'Bag Drop' }

function Row({
  s,
  showBrand,
  busy,
  onDone,
}: {
  s: TodoStep
  showBrand: boolean
  busy: boolean
  onDone: () => void
}) {
  const late = s.bucket === 'overdue'
  return (
    <li
      className="flex items-start gap-3 rounded-md bg-bg2 px-3 py-2"
      data-testid="todo-row"
      data-bucket={s.bucket}
    >
      <button
        type="button"
        disabled={busy}
        onClick={onDone}
        aria-label={`Mark done: ${s.title}`}
        title="Mark done"
        data-testid="todo-done"
        className="mt-0.5 shrink-0 rounded-full text-tx3 hover:text-emerald-400 disabled:opacity-50"
      >
        {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <CheckCircle2 className="h-5 w-5" strokeWidth={1.75} />}
      </button>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-tx">
          <span className="mr-2 rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-tx2 uppercase">
            {stepLabel(s)}
          </span>
          {s.title}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-tx3">
          <EventTypeIcon kind={s.event_kind} size="sm" />
          <span>
            {s.event_name} · {formatDay(s.event_date)}
          </span>
          {showBrand ? <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold">{BRAND[s.brand_id] || s.brand_id}</span> : null}
          <span className={late ? 'font-semibold text-red' : ''}>
            {formatDay(s.due)} · {dueWords(s.days)}
          </span>
          {s.plan_status === 'proposed' ? <span>Draft plan</span> : null}
        </p>
        {s.needs.length ? (
          <p className="mt-0.5 text-[11px] text-yel" data-testid="todo-needs">
            Still needs: {s.needs.join(', ')}.
          </p>
        ) : null}
      </div>
      <Link
        to="/calendar/lanes"
        className="shrink-0 rounded-full border border-bd px-3 py-1 text-xs font-semibold text-tx2 hover:text-tx"
      >
        Open plan
      </Link>
    </li>
  )
}

/** Every step still to do across the plans, by date, with a tick to mark each done. */
export function Todo() {
  const { brandId } = useBrand()
  const { isAll } = useBrandScope()
  const brand = isAll ? 'all' : brandId || 'all'
  const [data, setData] = useState<TodoResult | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => onAlertsChanged(() => setTick((t) => t + 1)), [])

  useEffect(() => {
    let cancelled = false
    void fetchTodo(brand).then((r) => {
      if (!cancelled) setData(r)
    })
    return () => {
      cancelled = true
    }
  }, [brand, tick])

  const done = useCallback(async (s: TodoStep) => {
    setBusyKey(s.key)
    setError(null)
    const r = await editPlanItem(s.brand_id, s.plan_id, s.item_id, { status: 'done' })
    setBusyKey(null)
    if (!r.ok) {
      setError(r.error || 'Could not mark that done.')
      return
    }
    notifyAlertsChanged()
  }, [])

  const groups = useMemo(() => groupTodo(data?.steps || []), [data])

  return (
    <div className="space-y-6">
      <PageIntro icon={ListChecks} badge="Planning" here="/todo" title="To do">
        {data ? todoSummary(data.counts) : 'Loading…'} Every step still to do across your plans, by date. Tick one when it is done.
      </PageIntro>

      {data && !data.ok ? <p className="text-sm text-red">{data.error}</p> : null}
      {error ? <p className="text-sm text-red">{error}</p> : null}

      {data?.ok && !data.steps.length ? (
        <p className="rounded-lg border border-dashed border-bd px-4 py-6 text-sm text-tx3" data-testid="todo-empty">
          Nothing to do in the next 30 days. When a plan has steps coming up, they appear here.
        </p>
      ) : null}

      {BUCKETS.map((b) =>
        groups[b].length ? (
          <section key={b} className="space-y-2" data-testid={`todo-${b}`}>
            <h2
              className={`text-[11px] font-bold tracking-widest uppercase ${b === 'overdue' ? 'text-red' : 'text-tx3'}`}
            >
              {BUCKET_LABEL[b]} · {groups[b].length}
            </h2>
            <ul className="space-y-1">
              {groups[b].map((s) => (
                <Row key={s.key} s={s} showBrand={isAll} busy={busyKey === s.key} onDone={() => void done(s)} />
              ))}
            </ul>
          </section>
        ) : null,
      )}
    </div>
  )
}
