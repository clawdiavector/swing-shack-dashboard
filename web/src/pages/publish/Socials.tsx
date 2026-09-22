import { ExternalLink, Share2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import {
  fetchAccounts,
  fetchSocialsOembed,
  fetchSocialsPosts,
  fetchSocialsStatus,
  type AccountsStatus,
  type SocialPost,
  type SocialsPostsPayload,
  type SocialsStatus,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'

type SocialsTab = 'posts' | 'health'
type DaysWindow = 30 | 90 | 365
type MediaFilter = 'all' | 'IMAGE' | 'VIDEO' | 'CAROUSEL_ALBUM'

const TAB_OPTIONS = [
  { id: 'posts', label: 'Posts' },
  { id: 'health', label: 'Health' },
]

const DAY_OPTIONS = [
  { id: '30', label: '30d' },
  { id: '90', label: '90d' },
  { id: '365', label: '365d' },
]

const TYPE_OPTIONS = [
  { id: 'all', label: 'All' },
  { id: 'IMAGE', label: 'Image' },
  { id: 'VIDEO', label: 'Video' },
  { id: 'CAROUSEL_ALBUM', label: 'Carousel' },
]

function resolveTab(raw: string | null): SocialsTab {
  return raw === 'health' ? 'health' : 'posts'
}

function resolveDays(raw: string | null): DaysWindow {
  if (raw === '30') return 30
  if (raw === '365') return 365
  return 90
}

function resolveType(raw: string | null): MediaFilter {
  if (raw === 'IMAGE' || raw === 'VIDEO' || raw === 'CAROUSEL_ALBUM') return raw
  return 'all'
}

function clampCaption(text: string | undefined, max = 140) {
  const t = (text || '').trim()
  if (t.length <= max) return t
  return `${t.slice(0, max - 1)}…`
}

function metaIntegrationState(accounts: AccountsStatus | null): string | null {
  if (!accounts?.categories) return null
  for (const cat of accounts.categories) {
    for (const item of cat.items || []) {
      if (item.id === 'meta' || item.id === 'instagram') return item.state || null
    }
  }
  return null
}

function SkeletonGrid() {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {Array.from({ length: 8 }, (_, i) => (
        <li key={i} className="aspect-square animate-pulse rounded-2xl bg-bg3" />
      ))}
    </ul>
  )
}

function PostThumb({ post, selected, onSelect }: { post: SocialPost; selected: boolean; onSelect: () => void }) {
  const [broken, setBroken] = useState(false)
  const src = post.thumbnail_url || post.media_url
  const typeLabel =
    post.media_type === 'VIDEO' ? 'Video' : post.media_type === 'CAROUSEL_ALBUM' ? 'Carousel' : 'Image'

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`overflow-hidden rounded-2xl border text-left transition-colors ${
        selected ? 'border-ac ring-1 ring-ac/40' : 'border-white/10 hover:border-ac/30'
      }`}
    >
      <div className="relative aspect-square bg-bg3">
        {src && !broken ? (
          <img
            src={src}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
            onError={() => setBroken(true)}
          />
        ) : (
          <span className="grid h-full place-items-center text-xs text-tx3">No thumbnail</span>
        )}
      </div>
      <div className="space-y-1 p-2 text-xs text-tx2">
        <p className="font-semibold text-tx3">{typeLabel}</p>
        {post.timestamp ? <p className="text-tx3">{formatStamp(post.timestamp)}</p> : null}
        <p className="line-clamp-2">
          {(post.like_count != null || post.comments_count != null) && (
            <span className="text-tx3">
              {post.like_count != null ? `❤ ${post.like_count}` : ''}
              {post.comments_count != null ? ` 💬 ${post.comments_count}` : ''}
              {' · '}
            </span>
          )}
          {clampCaption(post.caption, 140) || '—'}
        </p>
      </div>
    </button>
  )
}

function DetailPanel({ post, onClose }: { post: SocialPost; onClose: () => void }) {
  const [oembed, setOembed] = useState<{ html?: string; thumbnail_url?: string } | null>(null)

  useEffect(() => {
    if (!post.permalink) return
    let cancelled = false
    fetchSocialsOembed(post.permalink)
      .then((res) => {
        if (cancelled) return
        if (res.httpStatus === 502 || !res.ok) {
          setOembed(null)
          return
        }
        setOembed({ html: res.html, thumbnail_url: res.thumbnail_url })
      })
      .catch(() => {
        if (!cancelled) setOembed(null)
      })
    return () => {
      cancelled = true
    }
  }, [post.permalink])

  const mediaSrc = post.media_url || post.thumbnail_url || oembed?.thumbnail_url

  return (
    <aside className="glass sticky top-4 max-h-[calc(100vh-6rem)] space-y-4 overflow-y-auto rounded-2xl border border-white/10 p-4 lg:col-span-1">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-display text-lg font-semibold">Post detail</h2>
        <button type="button" className="text-xs text-tx3 hover:text-tx" onClick={onClose}>
          Close
        </button>
      </div>
      {mediaSrc ? (
        <img src={mediaSrc} alt="" className="max-h-64 w-full rounded-xl object-cover" />
      ) : null}
      {post.timestamp ? <p className="text-xs text-tx3">{formatStamp(post.timestamp)}</p> : null}
      {(post.like_count != null || post.comments_count != null) && (
        <p className="text-sm text-tx2">
          {post.like_count != null ? `${post.like_count} likes` : ''}
          {post.comments_count != null ? ` · ${post.comments_count} comments` : ''}
        </p>
      )}
      <p className="whitespace-pre-wrap text-sm text-tx2">{post.caption || 'No caption'}</p>
      {post.permalink ? (
        <a
          href={post.permalink}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm font-semibold text-ac underline"
        >
          Open on Instagram <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null}
    </aside>
  )
}

export function Socials() {
  const { brandId: brandIdRaw, brandLabel } = useBrand()
  const brandId = brandIdRaw ?? 'stick'
  const [params, setParams] = useSearchParams()
  const tab = resolveTab(params.get('tab'))
  const days = resolveDays(params.get('days'))
  const mediaType = resolveType(params.get('type'))
  const highlightPost = params.get('post') || ''

  const [status, setStatus] = useState<SocialsStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const [accounts, setAccounts] = useState<AccountsStatus | null>(null)
  const [postsPayload, setPostsPayload] = useState<SocialsPostsPayload | null>(null)
  const [allPosts, setAllPosts] = useState<SocialPost[]>([])
  const [postsLoading, setPostsLoading] = useState(false)
  const [loadMoreBusy, setLoadMoreBusy] = useState(false)
  const [postsError, setPostsError] = useState('')

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const setDays = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('days', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const setMediaType = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      if (id === 'all') p.delete('type')
      else p.set('type', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  useEffect(() => {
    setStatusLoading(true)
    fetchSocialsStatus()
      .then(setStatus)
      .catch(() => setStatus({ ok: false, graph_configured: false }))
      .finally(() => setStatusLoading(false))
    fetchAccounts(brandId)
      .then(setAccounts)
      .catch(() => setAccounts(null))
  }, [brandId])

  const loadPosts = useCallback(
    (after?: string, append = false) => {
      if (!append) {
        setPostsLoading(true)
        setPostsError('')
      } else {
        setLoadMoreBusy(true)
      }
      fetchSocialsPosts({ days, limit: 90, after })
        .then((payload) => {
          setPostsPayload(payload)
          const rows = payload.data || []
          setAllPosts((prev) => (append ? [...prev, ...rows] : rows))
        })
        .catch((e: Error) => {
          if (!append) {
            setAllPosts([])
            setPostsPayload(null)
            setPostsError(e.message || 'Could not load posts')
          }
        })
        .finally(() => {
          setPostsLoading(false)
          setLoadMoreBusy(false)
        })
    },
    [days],
  )

  useEffect(() => {
    if (tab !== 'posts') return
    loadPosts()
  }, [tab, loadPosts])

  const filteredPosts = useMemo(() => {
    if (mediaType === 'all') return allPosts
    return allPosts.filter((p) => p.media_type === mediaType)
  }, [allPosts, mediaType])

  const selectedPost = useMemo(() => {
    if (!highlightPost) return filteredPosts[0] || null
    return filteredPosts.find((p) => p.id === highlightPost) || allPosts.find((p) => p.id === highlightPost) || null
  }, [filteredPosts, allPosts, highlightPost])

  const [detailId, setDetailId] = useState<string | null>(null)
  const detailPost = useMemo(() => {
    const id = detailId || selectedPost?.id
    if (!id) return null
    return allPosts.find((p) => p.id === id) || null
  }, [detailId, selectedPost, allPosts])

  useEffect(() => {
    if (!highlightPost) return
    setDetailId(highlightPost)
    const p = new URLSearchParams(params)
    p.delete('post')
    setParams(p, { replace: true })
  }, [highlightPost, params, setParams])

  const metaState = metaIntegrationState(accounts)
  const brandWired = metaState === 'connected'
  const igShown = status?.ig_account_id

  const graphError = postsPayload?._meta?.graph_error

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Share2}
        here="/publish/socials"
        title="What's live"
        actions={
          statusLoading ? (
            <span className="h-6 w-32 animate-pulse rounded-full bg-bg3" />
          ) : (
            <span className="flex flex-wrap gap-2">
              <Badge tone={status?.graph_configured ? 'green' : 'gold'}>
                {status?.graph_configured ? 'Graph live' : 'Graph not wired'}
              </Badge>
              <Badge tone={status?.oembed_reachable ? 'green' : 'mute'}>
                oEmbed {status?.oembed_reachable ? 'reachable' : 'unreachable'}
              </Badge>
            </span>
          )
        }
      >
        Instagram posts from the default Meta account — not filtered by the brand chip alone.
      </PageIntro>

      <p className="rounded-2xl border border-yel/30 bg-yel/5 px-4 py-3 text-sm text-tx2">
        <span className="font-semibold text-yel">Brand honesty</span> — Socials reads the default Meta
        account, not the brand chip alone.
        {igShown ? (
          <span className="mt-1 block">
            Showing account <span className="font-mono text-tx">{igShown}</span>
            {brandLabel ? ` while ${brandLabel} is selected.` : '.'}
          </span>
        ) : null}
        {!brandWired && brandId ? (
          <span className="mt-1 block text-yel">
            {brandLabel || brandId}&apos;s Instagram is not wired — the posts below are the default
            account&apos;s.
          </span>
        ) : null}
        {brandWired && igShown ? (
          <span className="mt-1 block text-xs text-tx3">
            Active brand Meta state: {metaState}. Feed still comes from the env default until P5b threads
            brand_id through the API.
          </span>
        ) : null}
      </p>

      <FilterChips value={tab} options={TAB_OPTIONS} onChange={setTab} />

      {tab === 'health' ? (
        <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
          <h2 className="font-display text-lg font-semibold">Connection health</h2>
          <Tip text="Status includes a live ~3s oEmbed probe on each load — slow badge is normal.">
            <p className="text-xs text-tx3">Fetched once when you open this page (includes a live oEmbed probe).</p>
          </Tip>
          {!status ? (
            <p className="text-sm text-tx3">Loading…</p>
          ) : (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt>Graph configured</dt>
                <dd>{status.graph_configured ? '✓' : '✗'}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt>oEmbed reachable</dt>
                <dd>{status.oembed_reachable ? '✓' : '✗'}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt>IG account id</dt>
                <dd className="font-mono text-xs">{status.ig_account_id || '—'}</dd>
              </div>
              {status.reason ? (
                <div>
                  <dt className="text-tx3">Reason</dt>
                  <dd className="mt-1 text-tx2">{status.reason}</dd>
                </div>
              ) : null}
            </dl>
          )}
          <h3 className="pt-2 font-semibold text-tx">Brand wiring ({brandId})</h3>
          {!accounts ? (
            <p className="text-sm text-tx3">Loading accounts…</p>
          ) : (
            <p className="text-sm text-tx2">
              Meta / Instagram:{' '}
              <Badge tone={brandWired ? 'green' : metaState === 'partial' ? 'gold' : 'mute'}>
                {metaState || 'unknown'}
              </Badge>
              {' · '}
              <Link to="/ops?tab=accounts" className="text-ac underline">
                Accounts
              </Link>
            </p>
          )}
        </section>
      ) : (
        <>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-tx3">Window</p>
            <FilterChips value={String(days)} options={DAY_OPTIONS} onChange={setDays} />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-tx3">Media type (client filter)</p>
            <FilterChips value={mediaType} options={TYPE_OPTIONS} onChange={setMediaType} />
          </div>

          {!statusLoading && status && !status.graph_configured ? (
            <section className="rounded-2xl border border-yel/30 bg-yel/5 p-4 text-sm text-tx2">
              <p className="font-semibold text-yel">Connect Instagram</p>
              {status.reason ? <p className="mt-2">{status.reason}</p> : null}
              {status.ig_account_id ? (
                <p className="mt-2 text-xs">
                  Expected IG business account id: <span className="font-mono">{status.ig_account_id}</span>
                </p>
              ) : null}
              <p className="mt-3">
                Wire credentials on{' '}
                <Link to="/ops?tab=accounts" className="text-ac underline">
                  Accounts
                </Link>
                .
              </p>
            </section>
          ) : graphError ? (
            <p className="text-sm text-red">{graphError}</p>
          ) : postsLoading && !allPosts.length ? (
            <SkeletonGrid />
          ) : postsError ? (
            <p className="text-sm text-red">{postsError}</p>
          ) : filteredPosts.length === 0 && status?.graph_configured ? (
            <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
              No posts in the last {days} days — try 365.
            </p>
          ) : (
            <>
              {postsPayload?._meta ? (
                <p className="text-xs text-tx3">
                  {filteredPosts.length} posts shown · newest{' '}
                  {postsPayload._meta.newest ? formatStamp(String(postsPayload._meta.newest)) : '—'} · last{' '}
                  {postsPayload._meta.total_returned ?? allPosts.length} returned inside a {days}d window
                </p>
              ) : null}
              <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {filteredPosts.map((post) => (
                    <li key={post.id || post.permalink}>
                      <PostThumb
                        post={post}
                        selected={detailPost?.id === post.id}
                        onSelect={() => setDetailId(post.id || null)}
                      />
                    </li>
                  ))}
                </ul>
                {detailPost ? <DetailPanel post={detailPost} onClose={() => setDetailId(null)} /> : null}
              </div>
              {postsPayload?.paging?.has_more ? (
                <Tip text="Loads the next Graph page via ?after= cursor — not a full archive.">
                  <button
                    type="button"
                    disabled={loadMoreBusy}
                    className="rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50"
                    onClick={() => loadPosts(postsPayload.paging?.next_cursor || undefined, true)}
                  >
                    {loadMoreBusy ? 'Loading…' : 'Load more'}
                  </button>
                </Tip>
              ) : null}
            </>
          )}
        </>
      )}

      <ClassicLink href="/?page=socials" label="Socials" />
    </div>
  )
}
