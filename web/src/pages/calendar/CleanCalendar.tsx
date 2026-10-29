import { ChevronLeft, ChevronRight, Download, ExternalLink, Link2, MessageSquare, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { PageIntro } from '../../components/chrome'
import {
  actOnEntry,
  campaignPdfUrl,
  dayEntries,
  fetchCampaign,
  fetchCampaigns,
  fetchCleanMonth,
  makeShareLink,
  moveEntry,
  monthCells,
  pickStartView,
  shiftMonth,
  thisMonth,
  PHASE_COLOUR,
  VIEWS,
  type CampaignSummary,
  type CampaignTimeline,
  type CleanAction,
  type CleanEntry,
  type CleanMonth,
  type CleanView,
  type DayTarget,
} from '../../lib/cleanCalendar'

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MAX_PER_DAY = 3

// One look per view, so a glance says which list you are in.
const TILE: Record<CleanView, string> = {
  scheduled: 'border-ac/40 bg-ac/10',
  approval: 'border-yel/50 bg-yel/10',
  ideas: 'border-dashed border-tx3/50 bg-transparent',
  todo: 'border-[#8b80d8]/50 bg-[#8b80d8]/10',
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
  if (size === 'sm' || entry.kind === 'task') return null
  const words =
    entry.kind === 'idea'
      ? 'No picture yet. It gets made after you approve.'
      : entry.making
        ? 'Picture being made'
        : 'No picture'
  return (
    <div
      className={`${box} flex aspect-[4/5] items-center justify-center border border-dashed border-bd p-4 text-center text-sm text-tx3`}
    >
      {words}
    </div>
  )
}

function Tile({ entry, onOpen, draggable }: { entry: CleanEntry; onOpen: () => void; draggable?: boolean }) {
  const canDrag = Boolean(draggable && entry.movable)
  return (
    <button
      type="button"
      onClick={onOpen}
      title={canDrag ? `${entry.title} (drag to another day)` : entry.title}
      draggable={canDrag}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', JSON.stringify({ key: entry.key, kind: entry.kind, date: entry.date }))
        e.dataTransfer.effectAllowed = 'move'
      }}
      className={`flex w-full items-center gap-1.5 rounded-lg border p-1 text-left text-[11.5px] leading-tight font-semibold text-tx hover:border-tx2 ${canDrag ? 'cursor-grab active:cursor-grabbing' : ''} ${TILE[entry.view]} ${entry.making || entry.missed || entry.rejected ? 'opacity-55' : ''}`}
    >
      <Thumb entry={entry} size="sm" />
      <span className="line-clamp-2 min-w-0 flex-1">
        {entry.rejected
          ? `Sent back: ${entry.title}`
          : entry.missed
            ? `Missed: ${entry.title}`
            : entry.making
              ? `Being made: ${entry.title}`
              : entry.title}
      </span>
      {entry.comments.length ? (
        <MessageSquare className="h-3.5 w-3.5 shrink-0 text-blu" aria-label={`${entry.comments.length} comment(s)`} />
      ) : null}
    </button>
  )
}

// The day's count against the daily target, with a bar: solid is scheduled,
// light is made but waiting for a yes.
function TargetBadge({ t, onOpen }: { t: DayTarget; onOpen: () => void }) {
  const pct = (n: number) => `${Math.min(100, (n / t.target) * 100)}%`
  return (
    <button
      type="button"
      onClick={onOpen}
      title={`${t.done} scheduled and ${t.waiting} waiting, of ${t.target} a day`}
      className="block w-full rounded px-0.5 text-left hover:bg-bg3"
    >
      <span className="flex items-baseline justify-between gap-1 text-[11px] font-semibold text-tx2">
        <span>
          {t.done + t.waiting}/{t.target}
        </span>
        {t.lead ? <span className="truncate font-normal text-tx3">{t.lead.order[0].label}</span> : null}
      </span>
      <span className="mt-0.5 flex h-1 w-full overflow-hidden rounded-full bg-bg3">
        <span className="h-full bg-ac" style={{ width: pct(t.done) }} />
        <span className="h-full bg-ac/35" style={{ width: pct(t.waiting) }} />
      </span>
    </button>
  )
}

function TargetPanel({ day, t, onClose }: { day: string; t: DayTarget; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const missing = t.target - t.done - t.waiting
  const label = new Date(`${day}T12:00:00`).toLocaleDateString('en-ZA', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 md:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={`Daily target for ${label}`}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md space-y-4 rounded-2xl border border-bd bg-bg2 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-semibold">{label}</h2>
            <p className="text-sm text-tx2">
              {t.done} scheduled, {t.waiting} waiting for a yes,{' '}
              {missing > 0 ? `${missing} still to make` : 'target met'}. The target is {t.target} a day.
            </p>
          </div>
          <button type="button" aria-label="Close" className="rounded-full p-1.5 hover:bg-bg3" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>
        {t.lead ? (
          <div className="space-y-2 rounded-xl border border-bd p-3">
            <p className="text-sm">
              <span className="font-semibold">{t.lead.order[0].label} leads today</span>{' '}
              <span className="text-tx2">({t.lead.order.map((g) => `${g.label} ${g.count}`).join(', ')})</span>
            </p>
            {t.lead.push.length ? (
              <div>
                <p className="text-xs font-semibold text-tx3">
                  {t.lead.order[0].group === 'services' ? 'Services to show' : 'In stock to push'}
                </p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {t.lead.push.map((p) => (
                    <li key={p} className="rounded-full bg-bg3 px-2 py-0.5 text-xs">
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-tx3">No stock in this group is flagged to push right now.</p>
            )}
          </div>
        ) : null}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-tx3">
              <th className="pb-1 font-semibold">Where</th>
              <th className="pb-1 text-right font-semibold">Scheduled</th>
              <th className="pb-1 text-right font-semibold">Waiting</th>
              <th className="pb-1 text-right font-semibold">Target</th>
            </tr>
          </thead>
          <tbody>
            {t.slots.map((s) => {
              const gap = s.target - s.done - s.waiting
              return (
                <tr key={s.slot} className="border-t border-bd">
                  <td className="py-1.5">
                    {s.label}
                    {gap > 0 ? <span className="ml-1.5 text-xs text-yel">{gap} to make</span> : null}
                  </td>
                  <td className="py-1.5 text-right">{s.done}</td>
                  <td className="py-1.5 text-right">{s.waiting}</td>
                  <td className="py-1.5 text-right text-tx2">{s.target}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Detail({
  entry,
  position,
  onClose,
  onStep,
  onAct,
  onMove,
}: {
  entry: CleanEntry
  position: string
  onClose: () => void
  onStep: (step: number) => void
  onAct: (action: CleanAction, text: string) => Promise<string | null>
  onMove: (day: string) => Promise<string | null>
}) {
  const [writing, setWriting] = useState<CleanAction | null>(null)
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<string | null>(null)

  useEffect(() => {
    setWriting(null)
    setText('')
    setNote('')
    setDraft(null)
  }, [entry.key])

  async function saveCaption() {
    if (draft === null) return
    if (!draft.trim()) {
      setNote('The caption cannot be empty.')
      return
    }
    setBusy(true)
    const err = await onAct('edit', draft.trim())
    setBusy(false)
    if (err) setNote(err)
    else setDraft(null)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function press(action: CleanAction) {
    // Comment and Reject open the note box; its own Send button sends it.
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
            <button
              type="button"
              aria-label="Previous"
              className="rounded-full p-1.5 hover:bg-bg3"
              onClick={() => onStep(-1)}
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span>{position}</span>
            <button
              type="button"
              aria-label="Next"
              className="rounded-full p-1.5 hover:bg-bg3"
              onClick={() => onStep(1)}
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <button type="button" aria-label="Close" className="rounded-full p-1.5 hover:bg-bg3" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex flex-col gap-5 md:flex-row">
          {entry.kind === 'task' ? null : (
            <div className="md:w-[300px] md:shrink-0">
              <Thumb entry={entry} size="lg" />
            </div>
          )}
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
            {draft !== null ? (
              <div className="space-y-2">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={Math.min(14, Math.max(5, draft.split('\n').length + 1))}
                  aria-label="Caption"
                  className="w-full rounded-lg border border-bd bg-bg p-3 text-sm"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={saveCaption}
                    className="rounded-full bg-ac px-4 py-1.5 text-sm font-semibold text-bg disabled:opacity-50"
                  >
                    Save caption
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setDraft(null)
                      setNote('')
                    }}
                    className="rounded-full border border-bd px-4 py-1.5 text-sm font-semibold"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : entry.caption || entry.editable ? (
              <div className="space-y-1.5">
                {entry.caption ? (
                  <div className="rounded-lg bg-bg3 p-3 text-sm whitespace-pre-wrap">{entry.caption}</div>
                ) : null}
                {entry.editable ? (
                  <button
                    type="button"
                    onClick={() => setDraft(entry.caption || '')}
                    className="text-sm font-semibold text-ac hover:underline"
                  >
                    Edit caption
                  </button>
                ) : null}
              </div>
            ) : null}
            {entry.movable ? (
              <label className="flex flex-wrap items-center gap-2 text-sm text-tx2">
                Move to another day
                <input
                  type="date"
                  min={new Date().toLocaleDateString('en-CA')}
                  defaultValue={entry.date}
                  disabled={busy}
                  onChange={async (e) => {
                    const day = e.target.value
                    if (!day || day === entry.date) return
                    setBusy(true)
                    const err = await onMove(day)
                    setBusy(false)
                    if (err) setNote(err)
                  }}
                  className="rounded-lg border border-bd bg-bg px-2 py-1 text-sm text-tx"
                />
              </label>
            ) : null}
            {entry.link ? (
              <a
                href={entry.link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm font-semibold text-blu hover:underline"
              >
                See the post <ExternalLink className="h-3.5 w-3.5" />
              </a>
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
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void press(writing)
                }}
                placeholder={writing === 'reject' ? 'What should change? (needed)' : 'Your comment'}
                className="w-full rounded-lg border border-bd bg-bg p-2 text-sm"
              />
            ) : null}
            {writing ? (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void press(writing)}
                  className="rounded-full bg-tx px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
                >
                  {writing === 'reject' ? 'Send rejection' : 'Send comment'}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setWriting(null)
                    setNote('')
                  }}
                  className="rounded-full px-3 py-2 text-sm font-semibold text-tx2 hover:text-tx"
                >
                  Cancel
                </button>
                <span className="text-xs text-tx3">
                  {writing === 'reject'
                    ? 'It stays on its day marked Sent back, with your note, and leaves the Needs your OK count.'
                    : 'The note shows on the post.'}
                </span>
              </div>
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

function ShareBox({
  brand,
  brandName,
  planId,
  planTitle,
}: {
  brand: string
  brandName: string
  planId?: string
  planTitle?: string
}) {
  const [url, setUrl] = useState('')
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  async function make() {
    setErr('')
    const res = await makeShareLink(brand, 'Herman', planId)
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

  useEffect(() => {
    setUrl('')
    setErr('')
  }, [planId])

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
        Herman's link for {planTitle ? `the ${planTitle} timeline` : brandName}. No login, works for 14 days. He can
        approve, comment or reject.
      </p>
      <div className="flex gap-2">
        <input
          readOnly
          value={url}
          onFocus={(e) => e.target.select()}
          className="min-w-0 flex-1 rounded-lg border border-bd bg-bg px-2 py-1 text-xs"
        />
        <button
          type="button"
          onClick={() => void copy()}
          className="rounded-full bg-ac px-3 py-1 text-xs font-semibold text-bg"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      {err ? <p className="mt-1 text-xs text-red">{err}</p> : null}
    </div>
  )
}

function CampaignView({
  brand,
  planId,
  onOpen,
  version,
}: {
  brand: string
  planId: string
  onOpen: (entries: CleanEntry[], key: string) => void
  version: number
}) {
  const [t, setT] = useState<CampaignTimeline | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    void fetchCampaign(brand, planId).then((res) => {
      if (!live) return
      if (!res.ok) setError(res.error || 'Could not load the campaign.')
      else {
        setError('')
        setT(res)
      }
    })
    return () => {
      live = false
    }
  }, [brand, planId, version])

  if (error) return <p className="rounded-lg bg-red/10 px-3 py-2 text-sm text-red">{error}</p>
  if (!t) return <p className="text-sm text-tx3">Loading the campaign…</p>
  const posts = t.steps.map((s) => s.entry).filter((e): e is CleanEntry => Boolean(e))

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-bd bg-bg2 p-4">
        <h2 className="font-display text-2xl font-semibold">{t.title}</h2>
        <p className="text-sm text-tx2">{t.dates}. Every step from planning to the last post, in date order.</p>
        <div className="mt-3 flex h-3 gap-1">
          {t.phases.map((ph, i) => (
            <div
              key={i}
              className="rounded"
              style={{
                flex: ph.count,
                background: PHASE_COLOUR[ph.phase] || '#888',
              }}
              title={ph.phase}
            />
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-tx2">
          {t.phases.map((ph, i) => (
            <span key={i} className="inline-flex items-center gap-1.5">
              <i
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: PHASE_COLOUR[ph.phase] || '#888' }}
              />
              {ph.phase}
            </span>
          ))}
        </div>
      </div>
      {t.steps.length === 0 ? <p className="text-sm text-tx3">No steps in this plan yet.</p> : null}
      <ol className="space-y-2">
        {t.steps.map((s) => {
          const entry = s.entry
          return (
            <li key={s.item_id} className="flex gap-3 rounded-xl border border-bd bg-bg2 p-3">
              <span className="w-24 shrink-0 text-sm font-semibold">{s.when}</span>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 text-xs text-tx3">
                  <i
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ background: PHASE_COLOUR[s.phase] || '#888' }}
                  />
                  {s.phase}
                  {s.owner ? ` · ${s.owner}` : ''}
                </p>
                <p className="font-semibold">{s.title}</p>
                {s.shots.length ? (
                  <ul className="mt-1 list-disc pl-5 text-sm text-tx2">
                    {s.shots.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                ) : null}
                {entry ? (
                  <div className="mt-2 max-w-sm">
                    <Tile entry={entry} onOpen={() => onOpen(posts, entry.key)} />
                  </div>
                ) : null}
              </div>
              <span
                className={`h-fit shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.status === 'Done' ? 'bg-ac/15 text-ac' : s.status === 'Late' ? 'bg-red/15 text-red' : 'bg-bg3 text-tx2'}`}
              >
                {s.status}
              </span>
            </li>
          )
        })}
      </ol>
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
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([])
  const [campaignEntries, setCampaignEntries] = useState<CleanEntry[] | null>(null)
  const [version, setVersion] = useState(0)
  const [dropDay, setDropDay] = useState('')
  const todayIso = new Date().toLocaleDateString('en-CA')
  const [targetDay, setTargetDay] = useState<string | null>(null)
  const planId = params.get('campaign') || ''
  const plan = campaigns.find((c) => c.plan_id === planId)

  useEffect(() => {
    if (!brandId) return
    void fetchCampaigns(brandId).then((res) => setCampaigns(res.ok ? res.campaigns || [] : []))
  }, [brandId])

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

  const inView = useMemo(
    () => campaignEntries || (data?.entries || []).filter((e) => e.view === view),
    [campaignEntries, data, view],
  )
  const openIdx = inView.findIndex((e) => e.key === openKey)
  const open = openIdx >= 0 ? inView[openIdx] : null

  async function act(entry: CleanEntry, action: CleanAction, text: string): Promise<string | null> {
    if (!brandId) return 'Pick a brand first.'
    const res = await actOnEntry(brandId, {
      key: entry.key,
      kind: entry.kind,
      action,
      text,
      month,
    })
    if (!res.ok) return res.error || 'That did not save. Try again.'
    setCheer(res.message || 'Saved.')
    setTimeout(() => setCheer(''), 4000)
    // A comment or a caption edit keeps the same post open; approve and reject move on.
    if (action !== 'comment' && action !== 'edit') {
      const next = inView[openIdx + 1] || inView[openIdx - 1]
      setOpenKey(next && next.key !== entry.key ? next.key : null)
    }
    await load()
    setVersion((v) => v + 1)
    return null
  }

  async function move(entry: { key: string; kind: string; date: string }, day: string): Promise<string | null> {
    if (!brandId) return 'Pick a brand first.'
    if (day === entry.date) return null
    const res = await moveEntry(brandId, { key: entry.key, kind: entry.kind, date: day, month })
    if (!res.ok) {
      setCheer('')
      setError(res.error || 'Could not move it. Nothing was changed.')
      setTimeout(() => setError(''), 6000)
      return res.error || 'Could not move it. Nothing was changed.'
    }
    setCheer(res.message || 'Moved.')
    setTimeout(() => setCheer(''), 4000)
    await load()
    setVersion((v) => v + 1)
    return null
  }

  const pickCampaign = (id: string) => {
    const p = new URLSearchParams(params)
    if (id) p.set('campaign', id)
    else p.delete('campaign')
    setParams(p, { replace: true })
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
      <PageIntro
        here="/calendar/posts"
        title="Calendar"
        actions={<ShareBox brand={brandId} brandName={brandName} planId={plan?.plan_id} planTitle={plan?.title} />}
      >
        {brandName}. Pick a box to see one list at a time. Click any post to see it.
      </PageIntro>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-semibold" htmlFor="campaign-pick">
          Show
        </label>
        <select
          id="campaign-pick"
          value={plan ? planId : ''}
          onChange={(e) => pickCampaign(e.target.value)}
          className="rounded-full border border-bd bg-bg2 px-3 py-1.5 text-sm"
        >
          <option value="">All posts and plans</option>
          {campaigns.map((c) => (
            <option key={c.plan_id} value={c.plan_id}>
              One campaign: {c.title} ({c.when})
            </option>
          ))}
        </select>
        {plan ? (
          <a
            href={campaignPdfUrl(brandId, plan.plan_id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac"
          >
            <Download className="h-4 w-4" /> Export PDF
          </a>
        ) : null}
      </div>

      {cheer ? (
        <p className="rounded-lg bg-ac/10 px-3 py-2 text-sm text-ac" role="status">
          {cheer}
        </p>
      ) : null}

      {plan ? (
        <CampaignView
          brand={brandId}
          planId={plan.plan_id}
          version={version}
          onOpen={(entries, key) => {
            setCampaignEntries(entries)
            setOpenKey(key)
          }}
        />
      ) : null}

      <div className={plan ? 'hidden' : 'space-y-5'}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4" role="tablist">
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
            <button
              type="button"
              aria-label="Earlier month"
              className="rounded-full p-1.5 hover:bg-bg3"
              onClick={() => setQuery({ month: shiftMonth(month, -1) })}
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <span className="min-w-[9rem] text-center font-semibold">{data?.month_label || month}</span>
            <button
              type="button"
              aria-label="Next month"
              className="rounded-full p-1.5 hover:bg-bg3"
              onClick={() => setQuery({ month: shiftMonth(month, 1) })}
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
        </div>

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
            const past = cell.iso < todayIso
            return (
              <div
                key={cell.iso}
                onDragOver={(e) => {
                  if (past) return
                  e.preventDefault()
                  e.dataTransfer.dropEffect = 'move'
                  if (dropDay !== cell.iso) setDropDay(cell.iso)
                }}
                onDragLeave={() => setDropDay((d) => (d === cell.iso ? '' : d))}
                onDrop={(e) => {
                  e.preventDefault()
                  setDropDay('')
                  try {
                    const dragged = JSON.parse(e.dataTransfer.getData('text/plain'))
                    if (dragged?.key) void move(dragged, cell.iso)
                  } catch {
                    /* not one of our tiles */
                  }
                }}
                className={`min-h-[104px] space-y-1 rounded-xl border p-1.5 ${dropDay === cell.iso ? 'border-2 border-ac bg-ac/10' : 'border-bd bg-bg2'} ${past ? 'opacity-80' : ''}`}
              >
                <p className="px-0.5 text-xs font-semibold text-tx3">{cell.day}</p>
                {data?.targets?.[cell.iso] ? (
                  <TargetBadge t={data.targets[cell.iso]} onOpen={() => setTargetDay(cell.iso)} />
                ) : null}
                {items.slice(0, MAX_PER_DAY).map((e) => (
                  <Tile key={e.key} entry={e} onOpen={() => setOpenKey(e.key)} draggable />
                ))}
                {extra > 0 ? (
                  <button
                    type="button"
                    className="px-1 text-xs font-semibold text-tx2 hover:text-tx"
                    onClick={() => setOpenKey(items[MAX_PER_DAY].key)}
                  >
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
          <p className="hidden text-center text-sm text-tx3 md:block">
            Nothing in {VIEWS.find((v) => v.id === view)?.label} this month.
          </p>
        ) : null}
      </div>

      {targetDay && data?.targets?.[targetDay] ? (
        <TargetPanel day={targetDay} t={data.targets[targetDay]} onClose={() => setTargetDay(null)} />
      ) : null}

      {open ? (
        <Detail
          entry={open}
          position={`${openIdx + 1} of ${inView.length}`}
          onClose={() => {
            setOpenKey(null)
            setCampaignEntries(null)
          }}
          onStep={(step) => {
            const next = inView[(openIdx + step + inView.length) % inView.length]
            if (next) setOpenKey(next.key)
          }}
          onAct={(action, text) => act(open, action, text)}
          onMove={(day) => move(open, day)}
        />
      ) : null}
    </div>
  )
}
