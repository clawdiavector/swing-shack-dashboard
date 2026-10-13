import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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

const CARD_W = 256

/** Where the card sits: under the chip, kept inside the screen, flipped above
 *  when there is no room below. Fixed to the viewport, so it is not clipped by
 *  the grid or the glass panel around it. */
export function cardPosition(
  chip: { left: number; top: number; bottom: number },
  viewport: { w: number; h: number; x?: number },
  cardH = 190,
): { left: number; top: number } {
  const x = viewport.x ?? 0
  const left = Math.max(x + 8, Math.min(chip.left, x + viewport.w - CARD_W - 8))
  const below = chip.bottom + 4
  const top = below + cardH > viewport.h ? Math.max(8, chip.top - cardH - 4) : below
  return { left, top }
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
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const chipRef = useRef<HTMLSpanElement>(null)
  const timer = useRef<number | undefined>(undefined)
  const open = pos !== null

  const show = () => {
    window.clearTimeout(timer.current)
    const r = chipRef.current?.getBoundingClientRect()
    // The visual viewport is what the person sees; it is narrower than the
    // layout viewport when the page overflows sideways.
    const vv = window.visualViewport
    const view = vv
      ? { w: vv.width, h: vv.height, x: vv.offsetLeft }
      : { w: window.innerWidth, h: window.innerHeight }
    if (r) setPos(cardPosition(r, view))
  }
  const hideSoon = () => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setPos(null), 180)
  }

  useEffect(() => {
    if (!open) return
    const close = () => setPos(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  return (
    <span className="block" onMouseEnter={show} onMouseLeave={hideSoon} onFocus={show}>
      <span
        ref={chipRef}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        data-testid="ghost-chip"
        onClick={(e) => {
          e.stopPropagation()
          if (open) setPos(null)
          else show()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            e.stopPropagation()
            if (open) setPos(null)
            else show()
          }
          if (e.key === 'Escape') setPos(null)
        }}
        className="block max-w-full cursor-pointer truncate rounded-full border border-dashed border-tx3/50 bg-tx3/5 px-2 py-0.5 text-[10.5px] font-semibold text-tx2 opacity-60 hover:opacity-100"
      >
        {s.title}
      </span>
      {pos
        ? createPortal(
            <div
              role="dialog"
              aria-label={`Suggestion: ${s.title}`}
              data-testid="ghost-card"
              onClick={(e) => e.stopPropagation()}
              onMouseEnter={() => window.clearTimeout(timer.current)}
              onMouseLeave={hideSoon}
              style={{ position: 'fixed', left: pos.left, top: pos.top, width: CARD_W }}
              className="z-50 space-y-2 rounded-xl border border-bd bg-bg2 p-3 text-left shadow-xl"
            >
              <p className="text-[10px] font-bold tracking-widest text-tx3 uppercase">{SOURCE_LABEL[s.source]}</p>
              <p className="text-sm font-bold text-tx">{s.title}</p>
              <p className="flex flex-wrap items-center gap-2 text-xs text-tx2">
                {spanLabel(s.date, s.end)}
                {s.tier ? (
                  <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold tracking-wider">
                    {tierLabel(s.tier)}
                  </span>
                ) : null}
                {s.category ? <span className="text-tx3">{s.category}</span> : null}
              </p>
              {s.why ? <p className="line-clamp-4 text-xs text-tx3">{s.why}</p> : null}
              <div className="flex items-center gap-2 pt-1">
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
              </div>
            </div>,
            document.body,
          )
        : null}
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
