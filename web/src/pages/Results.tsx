import { Activity, BookOpen, Layers, LineChart, Search, Sparkles, TrendingUp } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { InsightPostThumb } from '../components/InsightPostThumb'
import { Badge, Button, IconTile, StatCard, Tip } from '../components/ui'
import { fetchToday, fetchTopPosts, type InsightPost, type TodayPanel } from '../lib/api'

const TABS: { href: string; label: string; hint: string; icon: LucideIcon }[] = [
  { href: '/results/week', label: 'This week', hint: 'Weekly report', icon: LineChart },
  { href: '/results/worked?tab=posts', label: 'What worked', hint: 'Insights', icon: Sparkles },
  {
    href: '/results/templates',
    label: 'Templates',
    hint: 'Brand bible + compose layouts',
    icon: Layers,
  },
  { href: '/?page=performance', label: 'Reach', hint: 'Performance', icon: Activity },
  { href: '/results/worked?tab=recipes', label: 'Learnings', hint: 'Recipes', icon: BookOpen },
  { href: '/?page=trends', label: 'Trends', hint: 'What is moving', icon: TrendingUp },
  { href: '/?page=seo', label: 'SEO', hint: 'Rankings and audit', icon: Search },
]

export function Results() {
  const { brandId, brandLabel } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [posts, setPosts] = useState<InsightPost[]>([])

  useEffect(() => {
    fetchToday(brandId)
      .then(setData)
      .catch(() => setData(null))
  }, [brandId])

  useEffect(() => {
    fetchTopPosts(brandId, 3)
      .then((p) => setPosts(p.posts || []))
      .catch(() => setPosts([]))
  }, [brandId])

  const published = data?.counts?.published ?? 0
  const brand = brandLabel || data?.active_brand_label || data?.active_brand_id || 'this brand'
  // The Flask /weekly-report route is auth-gated and lives outside the
  // React router. A plain <a href> does a full-page navigation and
  // carries the session cookie — the same way the OS shell renders
  // /daily and /publish. react-router-dom <Link to="..."> would try to
  // match the path client-side and either 404 or stay on the OS shell.
  const weeklyHref = `/weekly-report?brand=${encodeURIComponent(brandId || 'swing-shack')}`

  return (
    <div className="space-y-6">
      <PageIntro icon={Activity} badge="What worked" here="/results" title="Results">
        Reports and outcomes for {brand}. Daily already shows the headline numbers.
      </PageIntro>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          icon={Sparkles}
          label="Shipped"
          value={data ? published : '—'}
          hint="This week’s live posts"
          tone="green"
        />
        <a
          href={weeklyHref}
          className="glass block rounded-2xl border-[1.5px] border-yel/50 px-3 py-3 backdrop-blur-xl transition-colors hover:border-yel"
          title="Opens the full weekly report (authed)."
        >
          <div className="flex items-center justify-between gap-2">
            <LineChart className="h-5 w-5 text-yel" strokeWidth={2.5} />
            <span className="rounded-full bg-yel/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-yel uppercase">
              Open
            </span>
          </div>
          <p className="mt-2 font-display text-2xl font-semibold text-tx">Weekly</p>
          <p className="mt-0.5 text-[11px] font-semibold tracking-wide text-tx3 uppercase">
            Full weekly report
          </p>
        </a>
        <StatCard
          href="/?page=seo"
          icon={Search}
          label="SEO"
          value="Audit"
          hint="Rankings and gaps"
          tone="mute"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(380px,1fr)]">
        <HeroPanel
          icon={LineChart}
          kicker="Read this first"
          title="This week’s report"
          meta="What shipped, what moved, and what to do next Monday."
        >
          <a
            href={weeklyHref}
            className="inline-flex items-center gap-1.5 rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg transition-colors hover:bg-yel/90"
            title="Opens the full weekly report (authed, full-page)."
          >
            <LineChart className="h-4 w-4" strokeWidth={2.5} />
            Open weekly report
          </a>
          <Button to="/results/worked?tab=posts" icon={Sparkles} tone="ghost" tip="Open what worked — posts, reach, and recipes.">
            Insights
          </Button>
        </HeroPanel>
        <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
          <h2 className="font-display text-xl font-semibold">How to read it</h2>
          <ul className="mt-4 space-y-3 text-sm text-tx2">
            <li>
              <span className="font-semibold text-ac">Reach</span> — did anyone see it
            </li>
            <li>
              <span className="font-semibold text-yel">What worked</span> — repeat the winner
            </li>
            <li>
              <span className="font-semibold text-tx">Learnings</span> — write it down so next week is easier
            </li>
          </ul>
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">What worked lately</h2>
        {posts.length ? (
          <ul className="space-y-2">
            {posts.slice(0, 3).map((p, i) => {
              const key = p.id || String(i)
              const to = p.id
                ? `/results/worked?tab=posts&post=${encodeURIComponent(p.id)}`
                : '/results/worked?tab=posts'
              const line = p.plain_english || p.caption_excerpt || 'Recent post'
              return (
                <li key={key}>
                  <Tip text={`${p.verdict || 'Post'} — open in What worked.`}>
                    <Link
                      to={to}
                      className="glass flex items-center gap-3 rounded-2xl border-[1.5px] border-white/10 px-4 py-3 hover:border-ac/40"
                    >
                      <InsightPostThumb
                        post={p}
                        thumbKey={key}
                        className="h-16 w-16 shrink-0 rounded-xl object-cover"
                        placeholderClassName="grid h-16 w-16 shrink-0 place-items-center rounded-xl border border-bd text-[12px] text-tx3"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 text-sm font-medium">{line}</span>
                        {p.verdict ? (
                          <span className="mt-1 inline-block">
                            <Badge tone="green">{p.verdict}</Badge>
                          </span>
                        ) : null}
                      </span>
                    </Link>
                  </Tip>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
            No scored posts yet — open What worked, or wait for interpret to rank last week&apos;s feed.
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">All reports</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <a
            href={weeklyHref}
            className="glass flex items-start gap-3 rounded-2xl border-[1.5px] border-yel/50 p-4 backdrop-blur-xl transition-colors hover:border-yel"
            title="Opens the full weekly report (authed, full-page)."
          >
            <LineChart className="h-6 w-6 shrink-0 text-yel" strokeWidth={2.5} />
            <span>
              <span className="block font-display text-base font-semibold text-tx">This week</span>
              <span className="mt-0.5 block text-xs text-tx3">Weekly report</span>
            </span>
          </a>
          {TABS.map((tab) => (
            <IconTile key={tab.href} href={tab.href} icon={tab.icon} label={tab.label} hint={tab.hint} />
          ))}
        </div>
      </section>
    </div>
  )
}
