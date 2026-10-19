import { ExternalLink, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchTopPosts, type InsightPost, type InsightsPosts } from '../lib/api'
import { useBrand } from './BrandSwitch'
import { InsightPostThumb } from './InsightPostThumb'
import { formatStamp } from '../lib/stamp'
import { Badge } from './ui'

// "What worked lately" on the Results page: the best recent Instagram posts,
// each one named (caption, picture, date, link) with the numbers underneath.

function dateOnly(iso?: string): string {
  return iso ? iso.slice(0, 10) : ''
}

function daysAgo(iso?: string): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : Math.floor((Date.now() - t) / 86_400_000)
}

function verdictTone(verdict?: string): 'green' | 'gold' | 'red' | 'mute' {
  if (verdict === 'Top performer' || verdict === 'Above average') return 'green'
  if (verdict === 'Below average') return 'gold'
  if (verdict === 'Underperformer') return 'red'
  return 'mute'
}

// The brief Caption studio opens with for "Make another like this".
function briefFor(post: InsightPost, multiple: number | null): string {
  const result =
    post.engagementRate !== undefined
      ? ` (${post.engagementRate.toFixed(2)}% engagement${multiple !== null ? `, ${multiple.toFixed(1)}x our average` : ''})`
      : ''
  return (
    `Write a fresh take on a post that worked well${result}. Same topic, a different angle or format, in our voice.

` +
    `Original caption: ${post.caption_excerpt}`
  )
}

function PostRow({ post, rank, average }: { post: InsightPost; rank: number; average?: number }) {
  const key = post.id || String(rank)
  const rate = post.engagementRate
  const multiple = rate !== undefined && average ? rate / average : null
  const stats = [
    post.like_count ? `${post.like_count.toLocaleString()} ${post.like_count === 1 ? 'like' : 'likes'}` : '',
    post.comments_count ? `${post.comments_count.toLocaleString()} ${post.comments_count === 1 ? 'comment' : 'comments'}` : '',
  ].filter(Boolean)

  return (
    <li className="glass flex gap-3 rounded-2xl border-[1.5px] border-white/10 px-4 py-3">
      <span className="w-5 shrink-0 pt-1 font-display text-lg font-semibold text-tx3">{rank}</span>
      <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-xl border border-white/10 bg-white/5">
        <span className="absolute inset-0 grid place-items-center text-[11px] text-tx3">No image</span>
        <InsightPostThumb post={post} thumbKey={key} className="relative h-20 w-20 object-cover" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-sm font-medium text-tx">
          {post.caption_excerpt || 'Post with no caption saved'}
        </p>
        {post.timestamp ? <p className="mt-1 text-xs text-tx3">{formatStamp(post.timestamp)}</p> : null}
        <p className="mt-1 text-sm text-tx2">
          {rate !== undefined ? `${rate.toFixed(2)}% engagement` : 'Engagement unknown'}
          {multiple !== null && average ? ` · ${multiple.toFixed(1)}× the ${average.toFixed(2)}% average` : ''}
          {stats.length ? ` · ${stats.join(' · ')}` : ''}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {post.verdict ? <Badge tone={verdictTone(post.verdict)}>{post.verdict}</Badge> : null}
          {post.permalink ? (
            <a
              href={post.permalink}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs font-semibold text-ac hover:underline"
            >
              Open on Instagram <ExternalLink className="h-3 w-3" strokeWidth={2.5} />
            </a>
          ) : null}
          {post.caption_excerpt ? (
            <Link
              to={`/create/captions?brief=${encodeURIComponent(briefFor(post, multiple))}`}
              title="Open Caption studio with this post as the brief"
              className="inline-flex items-center gap-1 rounded-full bg-yel px-3 py-1 text-xs font-semibold text-bg hover:bg-yel/90"
            >
              <Sparkles className="h-3 w-3" strokeWidth={2.5} /> Make another like this
            </Link>
          ) : null}
          {post.id ? (
            <Link
              to={`/results/worked?tab=posts&post=${encodeURIComponent(post.id)}`}
              className="text-xs font-semibold text-tx3 hover:text-ac hover:underline"
            >
              More detail
            </Link>
          ) : null}
        </div>
      </div>
    </li>
  )
}

export function WorkedLately() {
  const { brandId, brandLabel } = useBrand()
  const [result, setResult] = useState<InsightsPosts | null>(null)
  // /api/insights/top-instagram-posts reads one shared Instagram store (Swing
  // Shack's) whatever brand is asked for, so showing it under Stick or Bag Drop
  // would put Swing Shack's posts on another company. Swing Shack only.
  const isSwingShack = brandId === 'swing-shack'

  useEffect(() => {
    if (!isSwingShack) return
    fetchTopPosts(brandId, 3)
      .then(setResult)
      .catch(() => setResult({ ok: false, posts: [] }))
  }, [brandId, isSwingShack])

  const posts = isSwingShack ? (result?.posts ?? []) : []
  const meta = isSwingShack ? result?._meta : undefined
  const age = daysAgo(meta?.fetched_at)

  return (
    <section>
      <h2 className="mb-1 font-display text-xl font-semibold">What worked lately</h2>
      <p className="mb-3 text-sm text-tx2">
        Your best recent Instagram posts, ranked by how much people engaged compared with your average. The point is to
        repeat the winners: same topic, a fresh take. Open a post to see what it said and showed, then make a new one.{' '}
        <Link to="/create" className="inline-flex items-center gap-1 font-semibold text-ac hover:underline">
          <Sparkles className="h-3 w-3" strokeWidth={2.5} /> Make a post in Create
        </Link>
      </p>

      {!isSwingShack ? (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
          Instagram results are only tracked for Swing Shack right now{brandLabel ? `, not ${brandLabel}` : ''}. Switch the
          brand to Swing Shack to see them.
        </p>
      ) : posts.length ? (
        <>
          <p className="mb-2 text-xs text-tx3">
            From the Swing Shack Instagram
            {meta?.total_scanned ? ` · ${meta.total_scanned} posts scanned` : ''}
            {meta?.average_engagement ? ` · average engagement ${meta.average_engagement}%` : ''}
            {meta?.fetched_at ? ` · data from ${dateOnly(meta.fetched_at)}` : ''}
            {age !== null && age > 7 ? ` (${age} days old)` : ''}
          </p>
          <ul className="space-y-2">
            {posts.slice(0, 3).map((p, i) => (
              <PostRow key={p.id || String(i)} post={p} rank={i + 1} average={meta?.average_engagement} />
            ))}
          </ul>
        </>
      ) : (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
          No scored posts yet — open What worked, wait for interpret, or connect Instagram in Accounts.
        </p>
      )}
    </section>
  )
}
