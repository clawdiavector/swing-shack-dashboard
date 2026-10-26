import { CheckCircle2, ExternalLink, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import '../fun.css'
import { burstConfetti } from '../lib/confetti'
import { toneFor } from '../lib/brandTone'
import { Mascot, type FunTone } from './fun'
import { useBrand } from './BrandSwitch'
import {
  fetchStoryCandidates,
  fetchStoriesWeek,
  fetchStoryMarks,
  fetchStoryReposts,
  fetchStorySuggestions,
  setStoryMark,
  setStoryRepostStatus,
  type StoryCandidate,
  type StoryRepost,
  type StorySuggestion,
} from '../lib/api'
import { BrandChip } from './BrandChip'

const TONE_MAP = { gold: 'gold', green: 'green', blue: 'blue', red: 'violet' } as const

const BTN = 'inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold'
const OPEN_BTN = `${BTN} bg-ac font-bold text-bg`
const OPEN_DARK = `${BTN} bg-neutral-900 font-bold text-white`
const DONE_BTN = `${BTN} border border-white/25 text-tx hover:border-ac hover:text-ac`
const SKIP_BTN = `${BTN} text-tx3 hover:text-tx`

/** Links people sent Foreman to share to Stories. Tap, use the app's own "Share to story", tick off. */
export function StoryReposts({
  brandIds,
  refreshKey = 0,
  alwaysShow = false,
}: {
  brandIds?: string[]
  /** Bump to reload the list, e.g. after a link is added elsewhere on the page. */
  refreshKey?: number
  /** Show the empty state instead of hiding the block when there is nothing to list. */
  alwaysShow?: boolean
}) {
  const [open, setOpen] = useState<StoryRepost[]>([])
  const [done, setDone] = useState<StoryRepost[]>([])
  const [ideas, setIdeas] = useState<StorySuggestion[]>([])
  const [weekCount, setWeekCount] = useState<number | null>(null)
  const [found, setFound] = useState<Record<string, StoryCandidate[]>>({})
  const [marks, setMarks] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState(false)
  const [leaving, setLeaving] = useState<string | null>(null)
  const [undo, setUndo] = useState<{ label: string; run: () => void } | null>(null)
  const { brands } = useBrand()
  const toneOf = (brandId: string): FunTone => {
    const row = brands.find((b) => b.id === brandId)
    return TONE_MAP[row?.tone ?? toneFor(brandId, row?.label || brandId, 0)]
  }

  const load = useCallback(() => {
    fetchStoryReposts()
      .then((r) => {
        setOpen(r.open)
        setDone(r.done_today)
        setFailed(false)
      })
      .catch(() => setFailed(true))
  }, [])
  useEffect(load, [load, refreshKey])
  useEffect(() => {
    fetchStorySuggestions()
      .then((r) => setIdeas(r.suggestions))
      .catch(() => setIdeas([]))
  }, [])

  useEffect(() => {
    fetchStoryMarks()
      .then((r) => setMarks(r.marks))
      .catch(() => setMarks({}))
  }, [])

  /** Shared / Not for us on an idea card or a scouted post; "clear" is Undo. */
  const weekKey = brandIds?.join(',') ?? ''
  const loadWeek = useCallback(() => {
    fetchStoriesWeek(weekKey ? weekKey.split(',') : undefined)
      .then((r) => setWeekCount(r.shared_this_week))
      .catch(() => setWeekCount(null))
  }, [weekKey])
  useEffect(loadWeek, [loadWeek, refreshKey])

  async function markKey(key: string, state: 'shared' | 'skipped' | 'clear', brand?: string) {
    setMarks((m) => {
      const next = { ...m }
      if (state === 'clear') delete next[key]
      else next[key] = state
      return next
    })
    try {
      const r = await setStoryMark(key, state, brand)
      setMarks(r.marks)
      loadWeek()
    } catch {
      fetchStoryMarks().then((r) => setMarks(r.marks)).catch(() => {})
    }
  }
  const ideaKey = (i: StorySuggestion) => `idea|${i.brand}|${i.date}|${i.kind}|${i.feature}`
  const postKey = (url: string) => `post|${url.replace('://www.', '://').replace(/\/+$/, '')}`

  const scoutKey = (brandIds?.length ? brandIds : ['swing-shack', 'stick']).join(',')
  useEffect(() => {
    for (const b of scoutKey.split(',')) {
      fetchStoryCandidates(b)
        .then((r) => setFound((f) => ({ ...f, [b]: r.posts })))
        .catch(() => setFound((f) => ({ ...f, [b]: [] })))
    }
  }, [scoutKey])

  const norm = (u: string) => u.replace('://www.', '://').replace(/\/+$/, '')
  const taken = new Set([...open, ...done].map((r) => norm(r.url)))
  const scoutRows = scoutKey
    .split(',')
    .flatMap((b) => (found[b] || []).map((c) => ({ brand: b, ...c })))
    .filter((c) => !taken.has(norm(c.url)) && !marks[postKey(c.url)])

  useEffect(() => {
    if (!undo) return
    const t = setTimeout(() => setUndo(null), 8000)
    return () => clearTimeout(t)
  }, [undo])

  /** Done or Skip on a scouted post: it leaves the list, with a few seconds to Undo. */
  function finishPost(url: string, state: 'shared' | 'skipped', brand: string) {
    void markKey(postKey(url), state, brand)
    setUndo({ label: state === 'shared' ? 'Marked done.' : 'Skipped.', run: () => void markKey(postKey(url), 'clear') })
  }

  const keep = (r: StoryRepost) => !brandIds?.length || brandIds.includes(r.brand)
  const openRows = open.filter(keep)
  const doneRows = done.filter(keep)
  const ideaRows = ideas.filter((i) => !brandIds?.length || brandIds.includes(i.brand))

  async function mark(id: string, status: 'open' | 'done' | 'removed', at?: { x: number; y: number }) {
    if (status === 'done') {
      if (at) burstConfetti(at.x, at.y, 45)
      setLeaving(id)
      await new Promise((r) => setTimeout(r, 280))
    }
    try {
      await setStoryRepostStatus(id, status)
    } finally {
      setLeaving(null)
      load()
      loadWeek()
    }
  }

  const nothing =
    !failed && !ideaRows.length && !scoutRows.length && !openRows.length && !doneRows.length
  if (nothing && !alwaysShow) return null

  return (
    <section
      className="fun-stories space-y-3"
      aria-label="Stories to share"
      data-testid="story-reposts"
    >
      <div className="fun-stories__head">
        <p className="fun-stories__title">Stories to share</p>
        {openRows.length + doneRows.length > 0 ? (
          <span className="fun-stories__count" aria-label={`${doneRows.length} shared today, ${openRows.length} to go`}>
            {doneRows.length} shared
            <span aria-hidden className="fun-dots">
              {[...doneRows.map(() => true), ...openRows.map(() => false)].slice(0, 10).map((on, i) => (
                <i key={i} data-on={on} />
              ))}
            </span>
            {openRows.length} to go
          </span>
        ) : null}
        {weekCount !== null ? (
          <span className="fun-stories__count" data-testid="stories-week-count">
            {weekCount} shared this week
          </span>
        ) : null}
      </div>
      <p className="text-sm text-tx2">
        <strong>1.</strong> Tap Open. <strong>2.</strong> In Instagram, tap Share to story. <strong>3.</strong> Come back and tap Done.
      </p>
      {undo ? (
        <p className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm text-tx" role="status">
          {undo.label}
          <button
            type="button"
            onClick={() => {
              undo.run()
              setUndo(null)
            }}
            className="inline-flex items-center gap-1 font-bold underline"
          >
            <Undo2 className="h-3.5 w-3.5" /> Undo
          </button>
        </p>
      ) : null}
      {failed ? <p className="text-sm text-tx2">Couldn’t load the story list. Try again in a minute.</p> : null}
      {ideaRows.length ? (
        <ul className="space-y-2" aria-label="Today's idea">
          {ideaRows.map((i) => {
            const state = marks[ideaKey(i)]
            return (
              <li
                key={`${i.brand}-${i.kind}-${i.feature}`}
                className={`fun-idea flex flex-wrap items-center gap-2 text-sm text-tx2${state ? ' opacity-60' : ''}`}
                data-tone={toneOf(i.brand)}
              >
                <BrandChip brandId={i.brand} />
                <span className="font-semibold text-tx">
                  {i.kind === 'stock'
                    ? 'Stock'
                    : i.kind === 'daily'
                      ? 'Daily'
                      : i.kind === 'moment'
                        ? 'Golf moment'
                        : i.kind === 'service'
                          ? 'Service'
                          : 'Retail'}
                  : {i.feature}
                </span>
                {i.repost_from ? null : <span>· our product, make the post from our photo{i.why ? ` (${i.why})` : ''}</span>}
                {i.repost_from ? <span>· repost from {i.repost_from.name}</span> : null}
                {i.repost_from?.look_for ? <span className="w-full text-xs text-tx3">{i.repost_from.look_for}</span> : null}
                <div className="flex w-full flex-wrap items-center gap-2 pt-1">
                  {state ? (
                    <>
                      <span className="text-sm font-semibold text-tx">{state === 'shared' ? 'Done' : 'Skipped'}</span>
                      <button
                        type="button"
                        onClick={() => void markKey(ideaKey(i), 'clear')}
                        aria-label={`Undo ${i.feature}`}
                        className="inline-flex items-center gap-1 text-sm font-semibold underline"
                      >
                        <Undo2 className="h-3.5 w-3.5" />
                        Undo
                      </button>
                    </>
                  ) : (
                    <>
                      {i.repost_from?.instagram ? (
                        <a href={i.repost_from.instagram} target="_blank" rel="noopener noreferrer" className={OPEN_DARK}>
                          Open Instagram <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      ) : null}
                      {i.repost_from?.facebook ? (
                        <a href={i.repost_from.facebook} target="_blank" rel="noopener noreferrer" className={OPEN_DARK}>
                          Open Facebook <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      ) : null}
                      <button type="button" onClick={() => void markKey(ideaKey(i), 'shared')} className={DONE_BTN}>
                        <CheckCircle2 className="h-4 w-4" /> Done
                      </button>
                      <button type="button" onClick={() => void markKey(ideaKey(i), 'skipped')} className={SKIP_BTN}>
                        <X className="h-4 w-4" /> Skip
                      </button>
                    </>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      ) : null}
      {scoutRows.length ? (
        <div className="space-y-2" aria-label="Posts worth sharing">
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Posts worth sharing</p>
          <ul className="space-y-2">
            {scoutRows.map((c) => (
              <li key={`${c.brand}-${c.url}`} className="flex items-start gap-3 rounded-xl border border-bd bg-surface/40 p-3 text-sm">
                {c.image ? (
                  <img
                    src={c.image}
                    alt=""
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    onError={(e) => (e.currentTarget.style.display = 'none')}
                    className="h-16 w-16 shrink-0 rounded-lg object-cover"
                  />
                ) : null}
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <BrandChip brandId={c.brand} />
                    <span className="font-semibold text-tx">{c.page}</span>
                    <span className="text-xs text-tx3">{c.posted}</span>
                  </div>
                  <p className="line-clamp-2 text-tx2">{c.caption || 'No caption'}</p>
                  <p className="text-xs text-tx3">
                    {c.why} · {(c.likes ?? 0).toLocaleString()} likes
                  </p>
                  {c.stock === 'match' ? (
                    <p className="text-xs font-semibold text-emerald-400">We stock this: {c.stock_name}</p>
                  ) : c.stock === 'none' ? (
                    <p className="text-xs font-semibold text-amber-400">Not on our stock list. Check we have it before sharing.</p>
                  ) : c.stock === 'brand-unlisted' ? (
                    <p className="text-xs font-semibold text-amber-400">We list nothing from this maker. Check before sharing.</p>
                  ) : null}
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <a href={c.url} target="_blank" rel="noopener noreferrer" className={OPEN_BTN}>
                      Open <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                    <button type="button" onClick={() => finishPost(c.url, 'shared', c.brand)} className={DONE_BTN}>
                      <CheckCircle2 className="h-4 w-4" /> Done
                    </button>
                    <button type="button" onClick={() => finishPost(c.url, 'skipped', c.brand)} className={SKIP_BTN}>
                      <X className="h-4 w-4" /> Skip
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <ul className="space-y-2">
        {openRows.map((r) => (
          <li
            key={r.id}
            className="fun-story flex flex-wrap items-center gap-2"
            data-tone={toneOf(r.brand)}
            data-leaving={leaving === r.id ? 'true' : undefined}
          >
            <BrandChip brandId={r.brand} />
            {r.added_by ? <span className="text-xs text-tx3">from {r.added_by}</span> : null}
            <span className="w-full text-sm font-semibold text-tx">{r.note || 'Saved post'}</span>
            <a href={r.url} target="_blank" rel="noopener noreferrer" className={OPEN_BTN}>
              Open <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <button
              type="button"
              onClick={(e) => {
                const b = e.currentTarget.getBoundingClientRect()
                void mark(r.id, 'done', { x: b.left + b.width / 2, y: b.top + b.height / 2 })
              }}
              className={DONE_BTN}
            >
              <CheckCircle2 className="h-4 w-4" /> Done
            </button>
            <button
              type="button"
              onClick={() => {
                void mark(r.id, 'removed')
                void markKey(postKey(r.url), 'skipped', r.brand)
                setUndo({
                  label: 'Skipped.',
                  run: () => {
                    void mark(r.id, 'open')
                    void markKey(postKey(r.url), 'clear')
                  },
                })
              }}
              className={SKIP_BTN}
            >
              <X className="h-4 w-4" /> Skip
            </button>
          </li>
        ))}
        {doneRows.map((r) => (
          <li key={r.id} className="fun-story fun-story--done flex flex-wrap items-center gap-2 text-tx3 line-through">
            <BrandChip brandId={r.brand} />
            <span className="text-sm">{r.note || r.url}</span>
            <button
              type="button"
              onClick={() => mark(r.id, 'open')}
              aria-label="Undo"
              className="ml-auto inline-flex items-center gap-1 text-xs no-underline hover:text-tx"
            >
              <Undo2 className="h-3.5 w-3.5" />
              Undo
            </button>
          </li>
        ))}
      </ul>
      {nothing ? (
        <p className="fun-empty" role="status">
          <Mascot tone="blue" />
          <span>The shelf is empty and I’m hungry. Feed me a link above.</span>
        </p>
      ) : null}
      {!failed && !openRows.length && doneRows.length ? (
        <p className="fun-empty" role="status">
          <Mascot tone="green" />
          <span>All shared. You’re on fire! New links from Foreman will land here.</span>
        </p>
      ) : null}
    </section>
  )
}
