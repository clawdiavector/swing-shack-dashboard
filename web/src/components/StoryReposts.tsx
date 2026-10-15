import { CheckCircle2, ExternalLink, Plus, Undo2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import '../fun.css'
import { burstConfetti } from '../lib/confetti'
import { toneFor } from '../lib/brandTone'
import { Mascot, type FunTone } from './fun'
import { useBrand } from './BrandSwitch'
import {
  addStoryRepost,
  fetchStoryCandidates,
  fetchStoryReposts,
  fetchStorySuggestions,
  setStoryRepostStatus,
  type StoryCandidate,
  type StoryRepost,
  type StorySuggestion,
} from '../lib/api'
import { BrandChip } from './BrandChip'

const TONE_MAP = { gold: 'gold', green: 'green', blue: 'blue', red: 'violet' } as const

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
  const [found, setFound] = useState<Record<string, StoryCandidate[]>>({})
  const [failed, setFailed] = useState(false)
  const [leaving, setLeaving] = useState<string | null>(null)
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
    .filter((c) => !taken.has(norm(c.url)))

  async function addFound(brand: string, c: StoryCandidate) {
    try {
      const firstLine = c.caption.split(/\r?\n/)[0].slice(0, 60)
      await addStoryRepost(brand, c.url, firstLine ? `${c.page}: ${firstLine}` : c.page)
    } finally {
      load()
    }
  }

  const keep = (r: StoryRepost) => !brandIds?.length || brandIds.includes(r.brand)
  const openRows = open.filter(keep)
  const doneRows = done.filter(keep)
  const ideaRows = ideas.filter((i) => !brandIds?.length || brandIds.includes(i.brand))

  async function mark(id: string, status: 'open' | 'done', at?: { x: number; y: number }) {
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
      </div>
      {failed ? <p className="text-sm text-tx2">Couldn’t load the story list. Try again in a minute.</p> : null}
      {ideaRows.length ? (
        <ul className="space-y-2" aria-label="Today's idea">
          {ideaRows.map((i) => (
            <li
              key={`${i.brand}-${i.kind}`}
              className="fun-idea flex flex-wrap items-center gap-2 text-sm text-tx2"
              data-tone={toneOf(i.brand)}
            >
              <BrandChip brandId={i.brand} />
              <span className="font-semibold text-tx">
                {i.kind === 'moment' ? 'Golf moment' : i.kind === 'service' ? 'Service' : 'Retail'}: {i.feature}
              </span>
              <span>· repost from {i.repost_from.name}</span>
              {i.repost_from.instagram ? (
                <a href={i.repost_from.instagram} target="_blank" rel="noopener noreferrer" className="underline hover:text-ac">
                  Instagram
                </a>
              ) : null}
              {i.repost_from.facebook ? (
                <a href={i.repost_from.facebook} target="_blank" rel="noopener noreferrer" className="underline hover:text-ac">
                  Facebook
                </a>
              ) : null}
              {i.repost_from.look_for ? <span className="w-full text-xs text-tx3">{i.repost_from.look_for}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {scoutRows.length ? (
        <div className="space-y-2" aria-label="Posts worth sharing">
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Posts worth sharing</p>
          <ul className="space-y-2">
            {scoutRows.map((c) => (
              <li key={`${c.brand}-${c.url}`} className="flex items-start gap-3 text-sm">
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
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-tx2 hover:border-ac hover:text-ac"
                  >
                    Look <ExternalLink className="h-3 w-3" />
                  </a>
                  <button
                    type="button"
                    onClick={() => addFound(c.brand, c)}
                    className="inline-flex items-center gap-1 rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-tx2 hover:border-ac hover:text-ac"
                  >
                    <Plus className="h-3 w-3" /> Add
                  </button>
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
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-display inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-sm font-semibold text-tx hover:border-ac/50"
            >
              {r.note || 'Open post'}
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            {r.added_by ? <span className="text-xs text-tx3">from {r.added_by}</span> : null}
            <button
              type="button"
              onClick={(e) => {
                const b = e.currentTarget.getBoundingClientRect()
                void mark(r.id, 'done', { x: b.left + b.width / 2, y: b.top + b.height / 2 })
              }}
              className="fun-story__done ml-auto inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-bold"
            >
              <CheckCircle2 className="h-4 w-4" />
              Shared
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
