import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  SOURCE_LABEL,
  approveSuggestion,
  fetchSuggestions,
  rejectSuggestion,
  spanLabel,
  undoMessage,
  undoSuggestion,
  type Suggestion,
  type Undo,
} from '../../../lib/calendarSuggestions'
import { actorName } from '../../../lib/plan'
import { tierLabel } from '../../../lib/planning'

export type Decided = { undo: Undo; title: string }

/** The faded suggestions for one month, and the three things you can do with them. */
export function useMonthSuggestions(brandId: string, month: string, enabled: boolean, onChanged: () => void) {
  const [items, setItems] = useState<Suggestion[]>([])
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [decided, setDecided] = useState<Decided | null>(null)
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

  const settle = useCallback(() => {
    setTick((t) => t + 1)
    onChanged()
  }, [onChanged])

  async function decide(s: Suggestion, verb: 'approve' | 'reject') {
    const name = actorName()
    if (!name) {
      setError('A name is needed so the calendar knows who decided.')
      return
    }
    setBusyKey(s.key)
    setError(null)
    const call = verb === 'approve' ? approveSuggestion : rejectSuggestion
    const r = await call(brandId, month, s.key, name)
    setBusyKey(null)
    if (!r.ok || !r.undo) {
      setError(r.error || 'That did not work.')
      return
    }
    setDecided({ undo: r.undo, title: s.title })
    settle()
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
    settle()
  }

  return {
    items: enabled && brandId ? items : [],
    busyKey,
    error,
    decided,
    approve: (s: Suggestion) => decide(s, 'approve'),
    reject: (s: Suggestion) => decide(s, 'reject'),
    undo,
    dismiss: () => setDecided(null),
    clearError: () => setError(null),
  }
}

/** A faded chip for one suggestion. Hover, focus or tap opens its card. */
export function GhostChip({
  s,
  busy,
  onApprove,
  onReject,
}: {
  s: Suggestion
  busy: boolean
  onApprove: () => void
  onReject: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <span
      className="relative block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false)
      }}
    >
      <span
        role="button"
        tabIndex={0}
        aria-expanded={open}
        data-testid="ghost-chip"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            e.stopPropagation()
            setOpen((v) => !v)
          }
        }}
        className="block max-w-full cursor-pointer truncate rounded-full border border-dashed border-tx3/50 bg-tx3/5 px-2 py-0.5 text-[10.5px] font-semibold text-tx2 opacity-60 hover:opacity-100"
      >
        {s.title}
      </span>
      {open ? (
        <span
          role="dialog"
          aria-label={`Suggestion: ${s.title}`}
          data-testid="ghost-card"
          onClick={(e) => e.stopPropagation()}
          className="absolute top-full left-0 z-30 w-64 pt-1"
        >
          <span className="block space-y-2 rounded-xl border border-bd bg-bg2 p-3 text-left shadow-xl">
            <span className="block text-[10px] font-bold tracking-widest text-tx3 uppercase">
              {SOURCE_LABEL[s.source]}
            </span>
            <span className="block text-sm font-bold text-tx">{s.title}</span>
            <span className="flex flex-wrap items-center gap-2 text-xs text-tx2">
              {spanLabel(s.date, s.end)}
              {s.tier ? (
                <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold tracking-wider">
                  {tierLabel(s.tier)}
                </span>
              ) : null}
              {s.category ? <span className="text-tx3">{s.category}</span> : null}
            </span>
            {s.why ? <span className="line-clamp-4 block text-xs text-tx3">{s.why}</span> : null}
            <span className="flex items-center gap-2 pt-1">
              <button
                type="button"
                disabled={busy}
                onClick={onApprove}
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
            </span>
          </span>
        </span>
      ) : null}
    </span>
  )
}

/** The toggle, plus the bar that says what just happened and offers Undo. */
export function SuggestionBar({
  show,
  onToggle,
  count,
  decided,
  busy,
  error,
  onUndo,
  onDismiss,
}: {
  show: boolean
  onToggle: (v: boolean) => void
  count: number
  decided: Decided | null
  busy: boolean
  error: string | null
  onUndo: () => void
  onDismiss: () => void
}) {
  return (
    <div className="space-y-2" data-testid="suggestion-bar">
      <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-tx2">
        <input
          type="checkbox"
          checked={show}
          onChange={(e) => onToggle(e.target.checked)}
          data-testid="suggestions-toggle"
        />
        Show suggestions
        {show ? <span className="text-tx3">({count} waiting this month, faded)</span> : null}
      </label>
      {decided ? (
        <div
          className="flex flex-wrap items-center gap-3 rounded-md border border-yel/30 bg-yel/10 px-3 py-2 text-xs text-tx"
          data-testid="undo-bar"
        >
          <span>{undoMessage(decided.undo.kind, decided.title)}</span>
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
    </div>
  )
}
