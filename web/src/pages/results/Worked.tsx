import { Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink } from '../../components/ui'
import {
  fetchAdCorrelation,
  fetchContentTrafficCorrelation,
  fetchIntelLearning,
  fetchLearn,
  fetchTopPosts,
  type AdCorrelation,
  type ContentTrafficCorrelation,
  type InsightPost,
  type InsightsPosts,
  type IntelLearning,
  type LearnSummary,
  type LearningRow,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'

type WorkedTab = 'posts' | 'recipes' | 'ctas' | 'patterns' | 'traffic'

const TAB_OPTIONS = [
  { id: 'posts', label: 'Posts' },
  { id: 'recipes', label: 'Recipes' },
  { id: 'ctas', label: 'CTAs' },
  { id: 'patterns', label: 'Patterns' },
  { id: 'traffic', label: 'Traffic' },
]

function resolveTab(raw: string | null): WorkedTab {
  if (raw === 'recipes' || raw === 'ctas' || raw === 'patterns' || raw === 'traffic') return raw
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

function DataAsOf({ map }: { map?: Record<string, string | null | undefined> }) {
  if (!map) return null
  const entries = Object.entries(map).filter(([, v]) => v)
  if (!entries.length) return null
  return (
    <p className="text-xs text-tx3">
      Data as of:{' '}
      {entries.map(([k, v]) => (
        <span key={k} className="mr-2">
          {k.replace(/_/g, ' ')} {v ? formatStamp(String(v)) : '—'}
        </span>
      ))}
    </p>
  )
}

function learningList(rows: LearningRow[] | undefined, empty: string) {
  if (!rows?.length) {
    return <p className="text-sm text-tx3">{empty}</p>
  }
  return (
    <ul className="space-y-2">
      {rows.map((row, i) => (
        <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
          <p className="font-medium text-tx">{row.title || 'Untitled'}</p>
          {row.why ? <p className="mt-1 text-tx2">{row.why}</p> : null}
          {row.kind ? <Badge tone="mute">{row.kind}</Badge> : null}
        </li>
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
  const [learning, setLearning] = useState<IntelLearning | null>(null)
  const [learnSummary, setLearnSummary] = useState<LearnSummary | null>(null)
  const [traffic, setTraffic] = useState<ContentTrafficCorrelation | null>(null)
  const [ads, setAds] = useState<AdCorrelation | null>(null)
  const [postsErr, setPostsErr] = useState('')
  const [learningErr, setLearningErr] = useState('')
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
    setLearningErr('')
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
    fetchIntelLearning()
      .then(setLearning)
      .catch((e: Error) => {
        setLearning(null)
        setLearningErr(e.message || 'GET /api/intel/learning failed')
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
    fetchAdCorrelation()
      .then(setAds)
      .catch(() => setAds(null))
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

  const loading = posts === null && learning === null && !postsErr && !learningErr
  const portfolioTabs = tab !== 'posts' && tab !== 'traffic'

  return (
    <div className="space-y-6">
      <PageIntro icon={Sparkles} here="/results/worked" title="What worked">
        Instagram posts for {brandLabel || brandId} plus portfolio learnings from flat files.
      </PageIntro>

      {loading ? <SkeletonBars n={5} /> : null}
      {postsErr ? <p className="text-sm text-red">{postsErr}</p> : null}
      {learningErr ? <p className="text-sm text-red">{learningErr}</p> : null}
      {trafficErr && tab === 'traffic' ? <p className="text-sm text-red">{trafficErr}</p> : null}

      {learnSummary?.headline ? (
        <div className="glass rounded-2xl border border-white/10 p-4 text-sm">
          <p className="font-semibold text-tx">
            Learn summary: {learnSummary.headline.verdict || '—'}
          </p>
          <p className="mt-1 text-tx2">
            {learnSummary.headline.winners ?? 0} winners · {learnSummary.headline.recipes ?? 0} recipes ·{' '}
            {learnSummary.headline.samples ?? 0} samples
          </p>
          <p className="mt-2 text-xs text-tx3">
            <span className="font-semibold">Portfolio-wide</span> — from /api/ops/learn/summary (not brand-scoped).
            {learnSummary.generated_at ? ` As of ${formatStamp(learnSummary.generated_at)}.` : ''}
          </p>
        </div>
      ) : null}

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />

      {tab === 'posts' ? (
        <>
          {postsMeta?.fetched_at ? (
            <p className="text-xs text-tx3">Instagram scan as of {formatStamp(postsMeta.fetched_at)}</p>
          ) : null}
          <ul className="space-y-2">
            {(posts || []).map((post, i) => {
              const key = post.id || String(i)
              const selected = highlightKey === key
              return (
                <li
                  key={key}
                  ref={(el) => {
                    rowRefs.current[key] = el
                  }}
                  className={`glass rounded-2xl border px-4 py-3 ${selected ? 'border-yel/50 ring-1 ring-yel/30' : 'border-white/10'}`}
                >
                  <div className="flex gap-3">
                    {post.thumbnail_url ? (
                      <img src={post.thumbnail_url} alt="" className="h-16 w-16 rounded-lg object-cover" />
                    ) : null}
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="font-medium text-tx">{post.plain_english || post.caption_excerpt || 'Post'}</p>
                      <p className="mt-1 flex flex-wrap gap-2 text-xs text-tx3">
                        {post.verdict ? <Badge tone="green">{post.verdict}</Badge> : null}
                        {post.engagementRate != null ? <span>{post.engagementRate.toFixed(2)}% engagement</span> : null}
                        {post.timestamp ? <span>{formatStamp(post.timestamp)}</span> : null}
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
                No scored posts yet — wait for interpret or connect Instagram in Accounts.
              </li>
            ) : null}
          </ul>
          {highlightKey === 'missing' && highlightPost ? (
            <p className="text-sm text-yel">That post is not in the top 8 — open Classic insights for the full list.</p>
          ) : null}
        </>
      ) : null}

      {portfolioTabs ? (
        <p className="rounded-2xl border border-bd/60 bg-bg2/40 px-4 py-3 text-sm text-tx2">
          <span className="font-semibold text-tx">Portfolio-wide</span> — this tab reads flat learn files, not the brand
          chip.
          <DataAsOf map={learning?.data_as_of} />
        </p>
      ) : null}

      {tab === 'recipes' && learning ? (
        <div className="space-y-6">
          <div>
            <h3 className="mb-2 font-semibold text-tx">What worked</h3>
            {learningList(learning.what_worked, 'No recipes yet — ship a few winners first.')}
          </div>
          <div>
            <h3 className="mb-2 font-semibold text-tx">What failed</h3>
            {learningList(learning.what_failed, 'No failures captured this cycle.')}
          </div>
        </div>
      ) : null}

      {tab === 'ctas' && learning ? (
        <div>{renderGenericList(learning.cta_rankings, 'No CTA rankings in cta-performance.json yet.')}</div>
      ) : null}

      {tab === 'patterns' && learning ? (
        <div className="space-y-4">
          {renderGenericList(learning.failure_patterns, 'No failure patterns logged yet.')}
          {learning.confidence_bands && Object.keys(learning.confidence_bands).length ? (
            <pre className="overflow-x-auto rounded-xl bg-bg2/50 p-3 text-xs text-tx2">
              {JSON.stringify(learning.confidence_bands, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}

      {tab === 'traffic' ? (
        <div className="space-y-6">
          <p className="text-xs text-tx3">
            Content ↔ traffic uses brand delegation via <code className="text-xs">brand_id={brandId}</code>.
          </p>
          {traffic ? (
            <>
              {renderGenericList(traffic.matches, 'No content-traffic matches in this window.')}
              {traffic.unmatched_spikes?.length ? (
                <div>
                  <h3 className="mb-2 font-semibold text-tx">Unmatched spikes</h3>
                  {renderGenericList(traffic.unmatched_spikes, '')}
                </div>
              ) : null}
            </>
          ) : null}
          {ads ? (
            <div className="rounded-2xl border border-white/10 p-4 text-sm">
              <h3 className="font-semibold text-tx">Paid media correlation</h3>
              {!ads.configured ? (
                <p className="mt-2 text-tx2">
                  Ads are not configured yet. Wire Google Ads / Meta exports so this card can join spend with GA4.
                </p>
              ) : (
                <p className="mt-2 text-tx2">{ads.combined_summary || 'Configured — see Classic for full detail.'}</p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-4">
        <ClassicLink href="/?page=insights" label="Classic insights" />
        <ClassicLink href="/?page=learning" label="Classic learnings" />
      </div>
    </div>
  )
}

function renderGenericList(items: unknown[] | undefined, empty: string) {
  if (!items?.length) {
    return empty ? <p className="text-sm text-tx3">{empty}</p> : null
  }
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm text-tx">
          {typeof item === 'string' ? item : JSON.stringify(item, null, 2)}
        </li>
      ))}
    </ul>
  )
}
