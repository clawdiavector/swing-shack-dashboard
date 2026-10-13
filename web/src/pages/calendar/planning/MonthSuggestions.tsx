import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  SOURCE_LABEL,
  approveSuggestion,
  fetchPillars,
  fetchSuggestions,
  rejectSuggestion,
  spanLabel,
  undoMessage,
  undoSuggestion,
  type PillarOption,
  type Suggestion,
  type Undo,
} from '../../../lib/calendarSuggestions'
import { EventTypeIcon, EventTypeLegend } from '../../../components/EventTypeIcon'
import { HoverChip } from './HoverChip'
import { notifyAlertsChanged } from '../../../lib/calendarAlerts'
import { actorName, planFromEvent } from '../../../lib/plan'
import { tierLabel } from '../../../lib/planning'

export type Decided = { undo: Undo; title: string }

/** The faded suggestions for one month, and the three things you can do with them. */
export function useMonthSuggestions(brandId: string, month: string, enabled: boolean, onChanged: () => void) {
  const [items, setItems] = useState<Suggestion[]>([])
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [decided, setDecided] = useState<Decided | null>(null)
  const [pillars, setPillars] = useState<PillarOption[]>([])
  const [planBusy, setPlanBusy] = useState(false)
  const [planNote, setPlanNote] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!enabled || !brandId) return
    let cancelled = false
    void fetchSuggestions(brandId, month).then((r) => {
      if (cancelled) return
      if (r.ok) setItems(r.items || [])
      else setError(r.error || 'Could not load the suggestions.')
    })
    return () => {
      cancelled = true
    }
  }, [brandId, month, enabled, tick])

  useEffect(() => {
    if (!enabled || !brandId) return
    let cancelled = false
    void fetchPillars(brandId).then((p) => {
      if (!cancelled) setPillars(p)
    })
    return () => {
      cancelled = true
    }
  }, [brandId, enabled])

  const settle = useCallback(() => {
    setTick((t) => t + 1)
    notifyAlertsChanged()
    onChanged()
  }, [onChanged])

  async function decide(s: Suggestion, verb: 'approve' | 'reject', pillar = '') {
    const name = actorName()
    if (!name) {
      setError('A name is needed so the calendar knows who decided.')
      return
    }
    setBusyKey(s.key)
    setError(null)
    const r =
      verb === 'approve'
        ? await approveSuggestion(brandId, month, s.key, name, pillar ? [pillar] : [])
        : await rejectSuggestion(brandId, month, s.key, name)
    setBusyKey(null)
    if (!r.ok || !r.undo) {
      setError(r.error || 'That did not work.')
      return
    }
    setPlanNote(null)
    setDecided({ undo: r.undo, title: s.title })
    settle()
  }

  /** From the approved date straight to a brief and a draft plan. */
  async function makePlan() {
    const key = decided?.undo.event_key
    if (!key) return
    setPlanBusy(true)
    setError(null)
    const r = await planFromEvent(brandId, key)
    setPlanBusy(false)
    if (!r.ok) {
      setError(r.error || 'Could not make the plan.')
      return
    }
    setPlanNote('Brief and draft plan made. Find it under Plan, then List, to check and approve.')
    notifyAlertsChanged()
    onChanged()
  }

  async function undo() {
    if (!decided) return
    setBusyKey(decided.undo.key)
    const r = await undoSuggestion(brandId, decided.undo)
    setBusyKey(null)
    if (!r.ok) {
      setError(r.error || 'Could not undo that.')
      return
    }
    setDecided(null)
    setPlanNote(null)
    settle()
  }

  return {
    items: enabled && brandId ? items : [],
    pillars,
    busyKey,
    error,
    decided,
    approve: (s: Suggestion, pillar?: string) => decide(s, 'approve', pillar),
    reject: (s: Suggestion) => decide(s, 'reject'),
    undo,
    makePlan,
    planBusy,
    planNote,
    dismiss: () => {
      setDecided(null)
      setPlanNote(null)
    },
    clearError: () => setError(null),
  }
}

export { cardPosition } from './HoverChip'

/** A faded chip for one suggestion. Hover, focus or tap opens its card. */
export function GhostChip({
  s,
  busy,
  pillars,
  onApprove,
  onReject,
}: {
  s: Suggestion
  busy: boolean
  pillars: PillarOption[]
  onApprove: (pillar: string) => void
  onReject: () => void
}) {
  const [pillar, setPillar] = useState('')
  // An important date has no pillar of its own, and without one it can never
  // get a brief, so it is asked for here. Entries that already carry one skip it.
  const needsPillar = !(s.pillars && s.pillars.length) && s.source === 'date' && pillars.length > 0
  return (
    <HoverChip
      chipTestId="ghost-chip"
      cardTestId="ghost-card"
      cardLabel={`Suggestion: ${s.title}`}
      chipClass="flex max-w-full cursor-pointer items-center gap-1 rounded-full border border-dashed border-tx3/50 bg-tx3/5 px-1.5 py-0.5 text-[10.5px] font-semibold text-tx2 opacity-60 hover:opacity-100"
      chip={
        <>
          <EventTypeIcon kind={s.kind} size="sm" className="!border-0 !bg-transparent !p-0" />
          <span className="min-w-0 truncate">{s.title}</span>
        </>
      }
    >
      <p className="flex items-center gap-2 text-[10px] font-bold tracking-widest text-tx3 uppercase">
        {SOURCE_LABEL[s.source]}
        <EventTypeIcon kind={s.kind} size="sm" withLabel />
      </p>
      <p className="text-sm font-bold text-tx">{s.title}</p>
      <p className="flex flex-wrap items-center gap-2 text-xs text-tx2">
        {spanLabel(s.date, s.end)}
        {s.tier ? (
          <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold tracking-wider">{tierLabel(s.tier)}</span>
        ) : null}
        {s.category ? <span className="text-tx3">{s.category}</span> : null}
      </p>
      {s.why ? <p className="line-clamp-4 text-xs text-tx3">{s.why}</p> : null}
      {needsPillar ? (
        <label className="block text-xs text-tx2">
          What is it for?
          <select
            value={pillar}
            onChange={(e) => setPillar(e.target.value)}
            data-testid="ghost-pillar"
            className="mt-1 w-full rounded border border-bd bg-bg px-2 py-1 text-sm text-tx"
          >
            <option value="">Choose a pillar</option>
            {pillars.map((p) => (
              <option key={p.pillar_id} value={p.pillar_id}>
                {p.name || p.pillar_id}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          disabled={busy || (needsPillar && !pillar)}
          title={needsPillar && !pillar ? 'Choose what it is for first, so it can get a brief' : undefined}
          onClick={() => onApprove(pillar)}
          data-testid="ghost-approve"
          className="inline-flex items-center gap-1 rounded-full border border-yel/40 bg-yel/15 px-3 py-1 text-xs font-semibold text-yel hover:bg-yel/25 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onReject}
          data-testid="ghost-reject"
          className="rounded-full border border-bd px-3 py-1 text-xs font-semibold text-tx2 hover:text-tx disabled:opacity-60"
        >
          Reject
        </button>
      </div>
    </HoverChip>
  )
}

/** The toggle, plus the bar that says what just happened and offers Undo. */
export function SuggestionBar({
  show,
  onToggle,
  count,
  showPlans = false,
  onTogglePlans,
  planStepCount = 0,
  decided,
  busy,
  error,
  onUndo,
  onDismiss,
  onMakePlan,
  planBusy = false,
  planNote = null,
}: {
  show: boolean
  onToggle: (v: boolean) => void
  count: number
  showPlans?: boolean
  onTogglePlans?: (v: boolean) => void
  planStepCount?: number
  decided: Decided | null
  busy: boolean
  error: string | null
  onUndo: () => void
  onDismiss: () => void
  onMakePlan?: () => void
  planBusy?: boolean
  planNote?: string | null
}) {
  return (
    <div className="space-y-2" data-testid="suggestion-bar">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-tx2">
          <input
            type="checkbox"
            checked={show}
            onChange={(e) => onToggle(e.target.checked)}
            data-testid="suggestions-toggle"
          />
          Show suggestions
          {show ? <span className="text-tx3">({count} waiting this month, grey)</span> : null}
        </label>
        {onTogglePlans ? (
          <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-tx2">
            <input
              type="checkbox"
              checked={showPlans}
              onChange={(e) => onTogglePlans(e.target.checked)}
              data-testid="plan-steps-toggle"
            />
            Show draft plan steps
            {showPlans ? <span className="text-tx3">({planStepCount} this month, yellow)</span> : null}
          </label>
        ) : null}
      </div>
      {decided ? (
        <div
          className="flex flex-wrap items-center gap-3 rounded-md border border-yel/30 bg-yel/10 px-3 py-2 text-xs text-tx"
          data-testid="undo-bar"
        >
          <span>{undoMessage(decided.undo.kind, decided.title)}</span>
          {decided.undo.kind === 'approve' && decided.undo.event_key && onMakePlan && !planNote ? (
            <button
              type="button"
              disabled={busy || planBusy}
              onClick={onMakePlan}
              data-testid="make-plan-button"
              className="inline-flex items-center gap-1 rounded-full border border-yel/40 bg-yel/20 px-3 py-1 font-bold text-yel hover:bg-yel/30 disabled:opacity-60"
            >
              {planBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              Make a plan
            </button>
          ) : null}
          {planNote ? <span className="text-tx2">{planNote}</span> : null}
          <button
            type="button"
            disabled={busy}
            onClick={onUndo}
            data-testid="undo-button"
            className="font-bold text-yel hover:underline disabled:opacity-60"
          >
            Undo
          </button>
          <button type="button" onClick={onDismiss} className="text-tx3 hover:text-tx">
            Dismiss
          </button>
        </div>
      ) : null}
      {error ? <p className="text-xs text-red">{error}</p> : null}
      <EventTypeLegend />
    </div>
  )
}
