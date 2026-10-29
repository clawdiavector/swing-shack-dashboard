import { ChevronLeft, ChevronRight, Link2, MessageSquare, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { PageIntro } from '../../components/chrome'
import {
  actOnEntry,
  dayEntries,
  fetchCleanMonth,
  makeShareLink,
  monthCells,
  pickStartView,
  shiftMonth,
  thisMonth,
  VIEWS,
  type CleanAction,
  type CleanEntry,
  type CleanMonth,
  type CleanView,
} from '../../lib/cleanCalendar'

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MAX_PER_DAY = 3

// One look per view, so a glance says which list you are in.
const TILE: Record<CleanView, string> = {
  scheduled: 'border-ac/40 bg-ac/10',
  approval: 'border-yel/50 bg-yel/10',
  ideas: 'border-dashed border-tx3/50 bg-transparent',
}

function Thumb({ entry, size }: { entry: CleanEntry; size: 'sm' | 'lg' }) {
  const box = size === 'sm' ? 'h-9 w-[29px] rounded' : 'w-full max-w-[360px] rounded-xl'
  if (entry.image) {
    return (
      <img
        src={entry.image}
        alt={size === 'lg' ? `The image for ${entry.title}` : ''}
        loading="lazy"
        className={`${box} shrink-0 object-cover ${size === 'lg' ? 'aspect-[4/5]' : ''}`}
      />
    )
  }
  if (size === 'sm') return null
  const words =
    entry.kind === 'idea' ? 'No picture yet. It gets made after you approve.' : entry.making ? 'Picture being made' : 'No picture'
  return (
    <div className={`${box} flex aspect-[4/5] items-center justify-center border border-dashed border-bd p-4 text-center text-sm text-tx3`}>
      {words}
    </div>
  )
}

function Tile({ entry, onOpen }: { entry: CleanEntry; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      title={entry.title}
      className={`flex w-full items-center gap-1.5 rounded-lg border p-1 text-left text-[11.5px] leading-tight font-semibold text-tx hover:border-tx2 ${TILE[entry.view]} ${entry.making ? 'opacity-55' : ''}`}
    >
      <Thumb entry={entry} size="sm" />
      <span className="line-clamp-2 min-w-0 flex-1">{entry.making ? `Being made: ${entry.title}` : entry.title}</span>
      {entry.comments.length ? (
        <MessageSquare className="h-3.5 w-3.5 shrink-0 text-blu" aria-label={`${entry.comments.length} comment(s)`} />
      ) : null}
    </button>
  )
}

function Detail({
  entry,
  position,
  onClose,
  onStep,
  onAct,
}: {
  entry: CleanEntry
  position: string
  onClose: () => void
  onStep: (step: number) => void
  onAct: (action: CleanAction, text: string) => Promise<string | null>
}) {
  const [writing, setWriting] = useState<CleanAction | null>(null)
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setWriting(null)
    setText('')
    setNote('')
  }, [entry.key])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function press(action: CleanAction) {
    if (action !== 'approve' && writing !== action) {
      setWriting(action)
      setNote('')
      return
    }
    if (action !== 'approve' && !text.trim()) {
      setNote(action === 'reject' ? 'Say what should change first.' : 'Write a comment first.')
      return
    }
    setBusy(true)
    const err = await onAct(action, text.trim())
    setBusy(false)
    if (err) setNote(err)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 md:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={entry.title}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-3xl rounded-2xl border border-bd bg-bg2 p-5">
        <div className="mb-3 flex items-center justify-between gap-2 text-sm text-tx3">
          <div className="flex items-center gap-1">
            <button type="button" aria-label="Previous" className="rounded-full p-1.5 hover:bg-bg3" onClick={() => onStep(-1)}>
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span>{position}</span>
            <button type="button" aria-label="Next" className="rounded-full p-1.5 hover:bg-bg3" onClick={() => onStep(1)}>
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <button type="button" aria-label="Close" className="rounded-full p-1.5 hover:bg-bg3" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex flex-col gap-5 md:flex-row">
          <div className="md:w-[300px] md:shrink-0">
            <Thumb entry={entry} size="lg" />
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <p className="text-sm text-tx3">
              {entry.brand_name} · {entry.where} · {entry.when}
            </p>
            <h2 className="font-display text-2xl leading-snug font-semibold">{entry.title}</h2>
            <span
              className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${entry.view === 'scheduled' ? 'bg-ac/15 text-ac' : 'bg-yel/15 text-yel'}`}
            >
              {entry.status}
            </span>
            <p className="text-[15px]">
              <b>What it is:</b> {entry.what}
            </p>
            {entry.why ? (
              <p className="text-[15px]">
                <b>Why:</b> {entry.why}
              </p>
            ) : null}
            {entry.next ? (
              <p className="text-[15px]">
                <b>If you approve:</b> {entry.next}
              </p>
            ) : null}
            {entry.caption ? (
              <div className="rounded-lg bg-bg3 p-3 text-sm whitespace-pre-wrap">{entry.caption}</div>
            ) : null}
            {entry.comments.length ? (
              <div className="space-y-1">
                {entry.comments.slice(-4).map((c) => (
                  <p key={c.at + c.text} className="border-l-2 border-bd pl-2 text-sm text-tx2">
                    <b>{c.who}:</b> {c.text}
                  </p>
                ))}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2 pt-1">
              {entry.actions.map((a) => (
                <button
                  key={a}
                  type="button"
                  disabled={busy}
                  onClick={() => void press(a)}
                  className={
                    a === 'approve'
                      ? 'rounded-full bg-ac px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50'
                      : `rounded-full border border-bd px-4 py-2 text-sm font-semibold disabled:opacity-50 ${a === 'reject' ? 'text-red' : 'text-tx'}`
                  }
                >
                  {a === 'approve' ? 'Approve' : a === 'reject' ? 'Reject' : 'Comment'}
                </button>
              ))}
            </div>
            {writing ? (
              <textarea
                autoFocus
                rows={3}
                value={text}
                onChange={(e) => {
                  setText(e.target.value)
                  setNote('')
                }}
                placeholder={writing === 'reject' ? 'What should change? (needed)' : 'Your comment'}
                className="w-full rounded-lg border border-bd bg-bg p-2 text-sm"
              />
            ) : null}
            {note ? (
              <p className="text-sm text-red" role="status">
                {note}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function ShareBox({ brand, brandName }: { brand: string; brandName: string }) {
  const [url, setUrl] = useState('')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  async function make() {
    setErr('')
    const res = await makeShareLink(brand)
    if (!res.ok || !res.share_url) {
      setErr(res.error || 'Could not make the link.')
      return
    }
    setUrl(res.share_url)
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      setErr('Copy did not work. Select the link and copy it.')
    }
  }

  if (!url) {
    return (
      <div className="flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={() => void make()}
          className="inline-flex items-center gap-1.5 rounded-full border border-bd px-4 py-2 text-sm font-semibold hover:border-ac hover:text-ac"
        >
          <Link2 className="h-4 w-4" />
          Share with Herman
        </button>
        {err ? <p className="text-xs text-red">{err}</p> : null}
      </div>
    )
  }
  return (
    <div className="w-full max-w-md rounded-xl border border-bd bg-bg2 p-3 text-sm">
      <p className="mb-2 text-tx2">
        Herman's link for {brandName}. No login, works for 14 days. He can approve, comment or reject.
      </p>
      <div className="flex gap-2">
        <input readOnly value={url} onFocus={(e) => e.target.select()} className="min-w-0 flex-1 rounded-lg border border-bd bg-bg px-2 py-1 text-xs" />
        <button type="button" onClick={() => void copy()} className="rounded-full bg-ac px-3 py-1 text-xs font-semibold text-bg">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {err ? <p className="mt-1 text-xs text-red">{err}</p> : null}
    </div>
  )
}

export function CleanCalendar() {
  const { brandId, brandLabel } = useBrand()
  const [params, setParams] = useSearchParams()
  const month = params.get('month') || thisMonth()
  const viewParam = params.get('view') as CleanView | null
  const [data, setData] = useState<CleanMonth | null>(null)
  const [error, setError] = useState('')
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [cheer, setCheer] = useState('')

  const load = useCallback(async () => {
    if (!brandId) return
    const res = await fetchCleanMonth(brandId, month)
    if (!res.ok) {
      setError(res.error || 'Could not load the calendar.')
      return
    }
    setError('')
    setData(res)
  }, [brandId, month])

  useEffect(() => {
    void load()
  }, [load])

  const view: CleanView =
    viewParam && VIEWS.some((v) => v.id === viewParam) ? viewParam : data ? pickStartView(data.counts) : 'approval'

  const setQuery = (next: Record<string, string>) => {
    const p = new URLSearchParams(params)
    for (const [k, v] of Object.entries(next)) p.set(k, v)
    setParams(p, { replace: true })
  }

  const inView = useMemo(() => (data?.entries || []).filter((e) => e.view === view), [data, view])
  const openIdx = inView.findIndex((e) => e.key === openKey)
  const open = openIdx >= 0 ? inView[openIdx] : null

  async function act(entry: CleanEntry, action: CleanAction, text: string): Promise<string | null> {
    if (!brandId) return 'Pick a brand first.'
    const res = await actOnEntry(brandId, { key: entry.key, kind: entry.kind, action, text, month })
    if (!res.ok) return res.error || 'That did not save. Try again.'
    setCheer(res.message || 'Saved.')
    setTimeout(() => setCheer(''), 4000)
    if (action !== 'comment') {
      const next = inView[openIdx + 1] || inView[openIdx - 1]
      setOpenKey(next && next.key !== entry.key ? next.key : null)
    }
    await load()
    return null
  }

  if (!brandId) {
    return (
      <div className="space-y-6">
        <PageIntro here="/calendar/posts" title="Calendar" />
        <p className="text-tx2">Pick a brand at the top first. Each brand has its own calendar.</p>
      </div>
    )
  }

  const cells = monthCells(month)
  const hint = VIEWS.find((v) => v.id === view)?.hint
  const brandName = data?.brand_name || brandLabel || brandId

  return (
    <div className="space-y-5">
      <PageIntro here="/calendar/posts" title="Calendar" actions={<ShareBox brand={brandId} brandName={brandName} />}>
        {brandName}. Pick a box to see one list at a time. Click any post to see it.
      </PageIntro>

      <div className="grid grid-cols-3 gap-3" role="tablist">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={view === v.id}
            onClick={() => setQuery({ view: v.id })}
            className={`rounded-2xl border bg-bg2 p-3 text-left md:p-4 ${view === v.id ? 'border-2 border-ac' : 'border-bd hover:border-tx3'}`}
          >
            <span className="block font-display text-3xl font-semibold">{data ? data.counts[v.id] : '–'}</span>
            <span className="text-sm text-tx2">{v.label}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-tx2">{hint}</p>
        <div className="flex items-center gap-1">
          <button type="button" aria-label="Earlier month" className="rounded-full p-1.5 hover:bg-bg3" onClick={() => setQuery({ month: shiftMonth(month, -1) })}>
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="min-w-[9rem] text-center font-semibold">{data?.month_label || month}</span>
          <button type="button" aria-label="Next month" className="rounded-full p-1.5 hover:bg-bg3" onClick={() => setQuery({ month: shiftMonth(month, 1) })}>
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>

      {cheer ? <p className="rounded-lg bg-ac/10 px-3 py-2 text-sm text-ac" role="status">{cheer}</p> : null}
      {error ? <p className="rounded-lg bg-red/10 px-3 py-2 text-sm text-red">{error}</p> : null}

      {/* Month grid on wider screens. */}
      <div className="hidden grid-cols-7 gap-1.5 md:grid">
        {DOW.map((d) => (
          <p key={d} className="text-center text-[11px] font-bold tracking-wider text-tx3 uppercase">
            {d}
          </p>
        ))}
        {cells.map((cell, i) => {
          if (!cell) return <div key={`pad-${i}`} />
          const items = dayEntries(data?.entries || [], cell.iso, view)
          const extra = items.length - MAX_PER_DAY
          return (
            <div key={cell.iso} className="min-h-[104px] space-y-1 rounded-xl border border-bd bg-bg2 p-1.5">
              <p className="px-0.5 text-xs font-semibold text-tx3">{cell.day}</p>
              {items.slice(0, MAX_PER_DAY).map((e) => (
                <Tile key={e.key} entry={e} onOpen={() => setOpenKey(e.key)} />
              ))}
              {extra > 0 ? (
                <button type="button" className="px-1 text-xs font-semibold text-tx2 hover:text-tx" onClick={() => setOpenKey(items[MAX_PER_DAY].key)}>
                  +{extra} more
                </button>
              ) : null}
            </div>
          )
        })}
      </div>

      {/* A plain list on phones. */}
      <div className="space-y-2 md:hidden">
        {inView.length === 0 ? <p className="py-6 text-center text-sm text-tx3">Nothing here this month.</p> : null}
        {inView.map((e) => (
          <div key={e.key}>
            <p className="mb-1 text-xs font-semibold text-tx3">{e.when}</p>
            <Tile entry={e} onOpen={() => setOpenKey(e.key)} />
          </div>
        ))}
      </div>

      {data && inView.length === 0 ? (
        <p className="hidden text-center text-sm text-tx3 md:block">Nothing in {VIEWS.find((v) => v.id === view)?.label} this month.</p>
      ) : null}

      {open ? (
        <Detail
          entry={open}
          position={`${openIdx + 1} of ${inView.length}`}
          onClose={() => setOpenKey(null)}
          onStep={(step) => {
            const next = inView[(openIdx + step + inView.length) % inView.length]
            if (next) setOpenKey(next.key)
          }}
          onAct={(action, text) => act(open, action, text)}
        />
      ) : null}
    </div>
  )
}
