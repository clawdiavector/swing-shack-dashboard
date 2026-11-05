import { Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink } from '../../components/ui'
import {
  fetchContentTrafficCorrelation,
  fetchLearn,
  fetchTopPosts,
  type ContentTrafficCorrelation,
  type InsightPost,
  type InsightsPosts,
  type LearnSummary,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'
import { matchSentence, pageLabel, spikeSentence, trafficSentence } from '../../lib/trafficSummary'
import { bestPostSentence, learnSentence, postFormat, postWeekday } from '../../lib/workedSummary'

// Recipes, CTAs and Patterns were cut: they read flat, portfolio-wide files with stale dates.
// They are still in Classic learnings until they are brand-scoped and dated.
type WorkedTab = 'posts' | 'traffic'

const TAB_OPTIONS = [
  { id: 'posts', label: 'Posts' },
  { id: 'traffic', label: 'Traffic' },
]

// Plain-language media type for the "why it worked" strip.
function formatName(mediaType?: string): string | null {
  const t = (mediaType || '').toUpperCase()
  if (t === 'VIDEO') return 'Reels'
  if (t === 'CAROUSEL_ALBUM') return 'carousels'
  if (t === 'IMAGE') return 'photos'
  return null
}

// Weekday in the brands' own timezone (both are South African).
function weekdayName(timestamp?: string): string | null {
  if (!timestamp) return null
  const d = new Date(timestamp)
  if (Number.isNaN(d.getTime())) return null
  return `${d.toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'Africa/Johannesburg' })}s`
}

// Most common value, only if it covers at least two posts and beats a tie.
function topShare(values: (string | null)[]): { value: string; count: number } | null {
  const counts = new Map<string, number>()
  for (const v of values) if (v) counts.set(v, (counts.get(v) || 0) + 1)
  let best: { value: string; count: number } | null = null
  for (const [value, count] of counts) {
    if (!best || count > best.count) best = { value, count }
  }
  if (!best || best.count < 2) return null
  const tied = [...counts.values()].filter((c) => c === best!.count).length > 1
  return tied ? null : best
}

// Badge colour follows the verdict from get_top_instagram_posts; unknown verdicts stay neutral.
function verdictTone(verdict: string): 'green' | 'gold' | 'red' | 'mute' {
  if (verdict === 'Top performer' || verdict === 'Above average') return 'green'
  if (verdict === 'Below average') return 'gold'
  if (verdict === 'Underperformer') return 'red'
  return 'mute'
}

function resolveTab(raw: string | null): WorkedTab {
  if (raw === 'traffic') return raw
  return 'posts'
}

function SkeletonBars({ n = 4 }: { n?: number }) {
  return (
    <ul className="space-y-2">
      {Array.from({ length: n }, (_, i) => (
        <li key={i} className="h-14 animate-pulse rounded-2xl bg-bg3" />
      ))}
    </ul>
  )
}

export function Worked() {
  const { brandId: rawBrandId, brandLabel } = useBrand()
  const brandId: string = rawBrandId ?? 'swing-shack'
  const [params, setParams] = useSearchParams()
  const tab = resolveTab(params.get('tab'))
  const highlightPost = params.get('post') || params.get('hook_id') || ''
  const [posts, setPosts] = useState<InsightPost[] | null>(null)
  const [postsMeta, setPostsMeta] = useState<InsightsPosts['_meta'] | undefined>()
  const [learnSummary, setLearnSummary] = useState<LearnSummary | null>(null)
  const [traffic, setTraffic] = useState<ContentTrafficCorrelation | null>(null)
  const [postsErr, setPostsErr] = useState('')
  const [trafficErr, setTrafficErr] = useState('')
  const rowRefs = useRef<Record<string, HTMLLIElement | null>>({})

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const reload = useCallback(() => {
    setPostsErr('')
    setTrafficErr('')
    fetchTopPosts(brandId, 8)
      .then((payload) => {
        setPosts(payload.posts || [])
        setPostsMeta(payload._meta)
      })
      .catch((e: Error) => {
        setPosts(null)
        setPostsErr(e.message || 'GET /api/insights/top-instagram-posts failed')
      })
    fetchLearn()
      .then(setLearnSummary)
      .catch(() => setLearnSummary(null))
    fetchContentTrafficCorrelation(brandId, 30)
      .then(setTraffic)
      .catch((e: Error) => {
        setTraffic(null)
        setTrafficErr(e.message || 'GET /api/insights/content-traffic-correlation failed')
      })
  }, [brandId])

  useEffect(() => {
    reload()
  }, [reload])

  const highlightKey = useMemo(() => {
    if (!highlightPost || !posts?.length) return null
    const idx = posts.findIndex((p) => p.id === highlightPost)
    if (idx < 0) return 'missing'
    return posts[idx].id || String(idx)
  }, [posts, highlightPost])

  useEffect(() => {
    if (!highlightKey || highlightKey === 'missing') return
    const el = rowRefs.current[highlightKey]
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    const p = new URLSearchParams(params)
    p.delete('post')
    p.delete('hook_id')
    setParams(p, { replace: true })
  }, [highlightKey, params, setParams])

  const loading = posts === null && !postsErr

  return (
    <div className="space-y-6">
      <PageIntro icon={Sparkles} here="/results/worked" title="What worked">
        Which Instagram posts for {brandLabel || brandId} did well, and what we’ve learned from them.
      </PageIntro>

      {loading ? <SkeletonBars n={5} /> : null}
      {postsErr ? <p className="text-sm text-red">{postsErr}</p> : null}
      {trafficErr && tab === 'traffic' ? <p className="text-sm text-red">{trafficErr}</p> : null}

      {tab === 'posts' && posts?.length ? (
        <p className="text-base font-medium text-tx">{bestPostSentence(posts, postsMeta?.average_engagement)}</p>
      ) : null}

      {learnSummary?.headline ? (
        <div className="glass rounded-2xl border border-white/10 p-4 text-sm">
          <p className="font-semibold text-tx">{learnSentence(learnSummary.headline)}</p>
          <p className="mt-2 text-xs text-tx3">
            Covers all brands, not just {brandLabel || brandId}.
            {learnSummary.generated_at ? ` Updated ${formatStamp(learnSummary.generated_at)}.` : ''}
          </p>
        </div>
      ) : null}

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />

      {tab === 'posts' ? (
        <>
          <p className="text-xs text-tx3">
            Last {postsMeta?.window_days ?? 90} days
            {postsMeta?.fetched_at ? ` · Instagram scan as of ${formatStamp(postsMeta.fetched_at)}` : ''}
          </p>
          {(() => {
            const good = (posts || []).filter((p) => p.verdict === 'Top performer' || p.verdict === 'Above average')
            if (good.length < 3) return null
            const format = topShare(good.map((p) => formatName(p.media_type)))
            const day = topShare(good.map((p) => weekdayName(p.timestamp)))
            return (
              <div className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
                <p className="font-medium text-tx">Why these worked (a guess from {good.length} good posts)</p>
                {format || day ? (
                  <p className="mt-1 flex flex-wrap gap-2 text-xs text-tx3">
                    {format ? (
                      <span>
                        Mostly {format.value}: {format.count} of {good.length}
                      </span>
                    ) : null}
                    {day ? (
                      <span>
                        Mostly posted on {day.value}: {day.count} of {good.length}
                      </span>
                    ) : null}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-tx3">No clear pattern yet across these posts.</p>
                )}
              </div>
            )
          })()}
          <ul className="space-y-2">
            {(posts || []).map((post, i) => {
              const key = post.id || String(i)
              const selected = highlightKey === key
              const rate = post.engagementRate
              const avg = postsMeta?.average_engagement
              const ratio = rate != null && avg ? rate / avg : null
              // Median over the last 90 days (backend: WORKED_WINDOW_DAYS in insights_correlator.py).
              const reactions = [
                post.like_count ? `${post.like_count.toLocaleString()} ${post.like_count === 1 ? 'like' : 'likes'}` : null,
                post.comments_count
                  ? `${post.comments_count.toLocaleString()} ${post.comments_count === 1 ? 'comment' : 'comments'}`
                  : null,
              ]
                .filter(Boolean)
                .join(' · ')
              return (
                <li
                  key={key}
                  ref={(el) => {
                    rowRefs.current[key] = el
                  }}
                  className={`glass rounded-2xl border px-4 py-3 ${selected ? 'border-yel/50 ring-1 ring-yel/30' : 'border-white/10'}`}
                >
                  <div className="flex gap-3">
                    <span className="pt-0.5 font-display text-sm font-semibold text-tx3">#{i + 1}</span>
                    {post.thumbnail_url ? (
                      <img src={post.thumbnail_url} alt="" className="h-16 w-16 rounded-lg object-cover" />
                    ) : null}
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="line-clamp-2 font-medium text-tx">{post.caption_excerpt || 'Post with no caption saved'}</p>
                      {brandLabel ? <p className="mt-0.5 text-xs text-tx3">{brandLabel}</p> : null}
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-tx3">
                        <Badge tone="mute">{postFormat(post.media_type)}</Badge>
                        {post.verdict ? <Badge tone={verdictTone(post.verdict)}>{post.verdict}</Badge> : null}
                        {rate != null ? (
                          <span>
                            {rate.toFixed(2)}% engagement
                            {ratio != null && avg != null ? ` · ${ratio.toFixed(1)}× the ${avg.toFixed(2)}% median` : ''}
                          </span>
                        ) : null}
                        {reactions ? <span>{reactions}</span> : null}
                        {post.timestamp ? (
                          <span>
                            {postWeekday(post.timestamp)} {formatStamp(post.timestamp)}
                          </span>
                        ) : null}
                      </p>
                      {post.permalink ? (
                        <a href={post.permalink} className="mt-2 inline-block text-xs text-ac underline" target="_blank" rel="noreferrer">
                          Open on Instagram
                        </a>
                      ) : null}
                    </div>
                  </div>
                </li>
              )
            })}
            {!posts?.length && !postsErr ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-8 text-sm text-tx3">
                {postsMeta?.reason || 'No scored posts yet — wait for interpret or connect Instagram in Accounts.'}
              </li>
            ) : null}
          </ul>
          {highlightKey === 'missing' && highlightPost ? (
            <p className="text-sm text-yel">That post is not in the top 8 — open Classic insights for the full list.</p>
          ) : null}
        </>
      ) : null}

      {tab === 'traffic' ? (
        <div className="space-y-6">
          {traffic?._meta?.ga4_total_sessions != null ? (
            <p className="text-base font-medium text-tx">
              {trafficSentence(traffic._meta.ga4_total_sessions, traffic._meta.ga4_window)}
            </p>
          ) : null}
          {traffic?._meta?.top_pages?.length ? (
            <div>
              <h3 className="mb-2 font-semibold text-tx">Where visitors went</h3>
              <ul className="space-y-2">
                {traffic._meta.top_pages.slice(0, 5).map((pg) => (
                  <li
                    key={pg.path}
                    className="glass flex items-baseline justify-between gap-3 rounded-2xl border border-white/10 px-4 py-3 text-sm"
                  >
                    <span className="min-w-0 truncate font-medium text-tx">{pageLabel(pg.path)}</span>
                    <span className="shrink-0 text-xs text-tx3">
                      {pg.sessions} visits{pg.engagement ? ` · ${pg.engagement} stayed engaged` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {traffic?._meta?.ga4_daily_window ? (
            <div className="space-y-3">
              <h3 className="font-semibold text-tx">Posts followed by a jump in visits</h3>
              {traffic.matches?.length ? (
                <ul className="space-y-2">
                  {traffic.matches.slice(0, 5).map((m, i) => (
                    <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
                      <p className="font-medium text-tx">{matchSentence(m)}</p>
                      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-tx3">
                        <Badge tone="mute">{String(m.confidence || 'low')} confidence</Badge>
                        <span className="line-clamp-1">{String(m.post_caption_excerpt || 'Post')}</span>
                        {m.post_permalink ? (
                          <a href={String(m.post_permalink)} className="text-ac underline" target="_blank" rel="noreferrer">
                            Open on Instagram
                          </a>
                        ) : null}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-tx3">
                  No day in the last 30 had enough extra visits to count as a jump after a post.
                </p>
              )}
              {traffic.unmatched_spikes?.length ? (
                <>
                  <h3 className="font-semibold text-tx">Jumps with no post behind them</h3>
                  <ul className="space-y-2">
                    {traffic.unmatched_spikes.slice(0, 3).map((m, i) => (
                      <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm text-tx2">
                        {spikeSentence(m)}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              <p className="text-xs text-tx3">
                This is timing only. A jump the day of or after a post is a good hint, not proof. Ads, emails and word of
                mouth also bring visitors.
              </p>
            </div>
          ) : (
            <p className="text-xs text-tx3">
              We can&apos;t yet say which post sent visitors. Daily visit numbers from Google Analytics start arriving
              after the next overnight update.
            </p>
          )}
          <div className="rounded-2xl border border-white/10 p-4 text-sm">
            <h3 className="font-semibold text-tx">Paid ads</h3>
            <p className="mt-1 text-tx2">
              Ad spend and results for each brand are on the Trends page, with this month&apos;s budget and what to do
              next.
            </p>
            <Link to="/results/trends" className="mt-2 inline-block text-sm font-semibold text-ac hover:text-yel">
              See ad results
            </Link>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-4">
        <ClassicLink href="/?page=insights" label="Classic insights" text="Full insights" />
        <ClassicLink href="/?page=learning" label="Classic learnings" text="Full learnings" />
      </div>
    </div>
  )
}
