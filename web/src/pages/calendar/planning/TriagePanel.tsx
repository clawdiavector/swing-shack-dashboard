import { useCallback, useEffect, useRef, useState } from 'react'
import { EventTypeIcon } from '../../../components/EventTypeIcon'
import { notifyAlertsChanged } from '../../../lib/calendarAlerts'
import {
  approveSuggestion,
  fetchPillars,
  fetchTriage,
  laterSuggestion,
  rejectSuggestion,
  spanLabel,
  undoSuggestion,
  type PillarOption,
  type Suggestion,
  type Undo,
} from '../../../lib/calendarSuggestions'
import { actorName } from '../../../lib/plan'
import { tierLabel } from '../../../lib/planning'

type Done = { item: Suggestion; undo: Undo; what: string }

/** A key that means a pillar: 1, 2, 3 ... */
export function pillarForKey(key: string, pillars: PillarOption[]): PillarOption | null {
  if (!/^[1-9]$/.test(key)) return null
  return pillars[Number(key) - 1] || null
}

/** Sort the important dates one at a time: approve under a pillar (1, 2, 3), reject
 *  (R), not now (N), undo the last (U). Nothing here makes a plan: that happens when
 *  a date is approved from the grid, or when it gets close and the alert says so. */
export function TriagePanel({
  brandId,
  onClose,
  onChanged,
}: {
  brandId: string
  onClose: () => void
  onChanged: () => void
}) {
  const [queue, setQueue] = useState<Suggestion[] | null>(null)
  const [total, setTotal] = useState(0)
  const [pillars, setPillars] = useState<PillarOption[]>([])
  const [last, setLast] = useState<Done | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busyRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    void fetchTriage(brandId).then((r) => {
      if (cancelled) return
      if (r.ok) {
        setQueue(r.items || [])
        setTotal((r.items || []).length)
      } else setError(r.error || 'Could not load the dates.')
    })
    void fetchPillars(brandId).then((p) => !cancelled && setPillars(p))
    return () => {
      cancelled = true
    }
  }, [brandId])

  const current = queue?.[0] ?? null

  const act = useCallback(
    async (what: 'approve' | 'reject' | 'later', pillar?: PillarOption) => {
      if (!current || busyRef.current) return
      const name = actorName()
      if (!name) {
        setError('A name is needed so the calendar knows who decided.')
        return
      }
      busyRef.current = true
      setBusy(true)
      setError(null)
      const month = current.date.slice(0, 7)
      const r =
        what === 'approve'
          ? await approveSuggestion(brandId, month, current.key, name, pillar ? [pillar.pillar_id] : [])
          : what === 'reject'
            ? await rejectSuggestion(brandId, month, current.key, name)
            : await laterSuggestion(brandId, month, current.key, name)
      busyRef.current = false
      setBusy(false)
      if (!r.ok || !r.undo) {
        setError(r.error || 'That did not work.')
        return
      }
      const words = what === 'approve' ? `Added to the calendar as ${pillar?.name || pillar?.pillar_id}` : what === 'reject' ? 'Rejected' : 'Put off for two weeks'
      setLast({ item: current, undo: r.undo, what: words })
      setQueue((q) => (q ? q.slice(1) : q))
      notifyAlertsChanged()
      onChanged()
    },
    [brandId, current, onChanged],
  )

  const undoLast = useCallback(async () => {
    if (!last || busyRef.current) return
    busyRef.current = true
    setBusy(true)
    const r = await undoSuggestion(brandId, last.undo)
    busyRef.current = false
    setBusy(false)
    if (!r.ok) {
      setError(r.error || 'Could not undo that.')
      return
    }
    setQueue((q) => [last.item, ...(q || [])])
    setLast(null)
    setError(null)
    notifyAlertsChanged()
    onChanged()
  }, [brandId, last, onChanged])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && /^(input|textarea|select)$/i.test(el.tagName)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (k === 'escape') return onClose()
      if (k === 'r') return void act('reject')
      if (k === 'n') return void act('later')
      if (k === 'u') return void undoLast()
      const p = pillarForKey(k, pillars)
      if (p) void act('approve', p)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [act, undoLast, onClose, pillars])

  const position = queue ? total - queue.length + 1 : 0
  const btn = 'rounded-full border px-3 py-1.5 text-xs font-semibold disabled:opacity-50'

  return (
    <section className="space-y-3 rounded-xl border border-yel/30 bg-bg2 p-4" data-testid="triage-panel" aria-label="Sort your dates">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-tx">Sort your dates</h2>
          <p className="text-xs text-tx3">
            {queue === null
              ? 'Loading…'
              : current
                ? `${position} of ${total}. Use the keys, or the buttons.`
                : 'All sorted.'}
          </p>
        </div>
        <button type="button" onClick={onClose} className="text-xs text-tx3 hover:text-tx" data-testid="triage-close">
          Close (Esc)
        </button>
      </div>

      {queue && total > 0 ? (
        <div className="h-1 overflow-hidden rounded bg-bg" aria-hidden>
          <div className="h-full bg-yel" style={{ width: `${((total - queue.length) / total) * 100}%` }} />
        </div>
      ) : null}

      {current ? (
        <div className="space-y-2" data-testid="triage-card">
          <p className="flex flex-wrap items-center gap-2">
            <EventTypeIcon kind={current.kind} withLabel />
            {current.tier ? (
              <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-tx2">
                {tierLabel(current.tier)}
              </span>
            ) : null}
            {current.category ? <span className="text-xs text-tx3">{current.category}</span> : null}
          </p>
          <p className="font-display text-2xl leading-tight font-semibold text-tx" data-testid="triage-title">
            {current.title}
          </p>
          <p className="text-sm text-tx2">{spanLabel(current.date, current.end)}</p>
          {current.why ? <p className="max-w-2xl text-sm text-tx3">{current.why}</p> : null}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-tx3">Add it to the calendar as</span>
            {pillars.map((p, i) => (
              <button
                key={p.pillar_id}
                type="button"
                disabled={busy}
                onClick={() => void act('approve', p)}
                data-testid={`triage-approve-${i + 1}`}
                className={`${btn} border-yel/40 bg-yel/15 text-yel hover:bg-yel/25`}
              >
                <kbd className="mr-1.5 rounded bg-bg px-1 text-[10px]">{i + 1}</kbd>
                {p.name || p.pillar_id}
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={() => void act('reject')}
              data-testid="triage-reject"
              className={`${btn} border-bd text-tx2 hover:text-tx`}
            >
              <kbd className="mr-1.5 rounded bg-bg px-1 text-[10px]">R</kbd>Reject
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void act('later')}
              data-testid="triage-later"
              className={`${btn} border-bd text-tx2 hover:text-tx`}
            >
              <kbd className="mr-1.5 rounded bg-bg px-1 text-[10px]">N</kbd>Not now
            </button>
          </div>
        </div>
      ) : queue ? (
        <p className="text-sm text-tx2" data-testid="triage-done">
          Nothing left to sort. Dates you put off with Not now come back in two weeks.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 text-xs">
        <button
          type="button"
          disabled={busy || !last}
          onClick={() => void undoLast()}
          data-testid="triage-undo"
          className="font-semibold text-yel hover:underline disabled:text-tx3 disabled:no-underline"
        >
          <kbd className="mr-1.5 rounded bg-bg px-1 text-[10px]">U</kbd>Undo
        </button>
        {last ? (
          <span className="text-tx3" data-testid="triage-last">
            {last.what}: {last.item.title}
          </span>
        ) : null}
        {error ? <span className="text-red">{error}</span> : null}
      </div>
    </section>
  )
}
