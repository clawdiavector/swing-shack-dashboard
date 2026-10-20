import { Activity } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge, StatCard } from '../components/ui'
import { getJson } from '../lib/api'
import { ageDays, dateOnly } from '../lib/dataAge'

// Native Reach page. Reads the classic Reach (Performance) view's endpoints:
// GET /api/intel/performance  (GA4, website, Instagram, SEO movers, A/B tests)
// GET /api/intel/explain      (what the numbers mean, with next steps)

interface Performance {
  data_as_of: Record<string, string>
  ga4: { total_sessions: number; pages: { path: string; sessions: number; engRate: string }[] }
  instagram: {
    total_posts: number
    top_posts: { hook_text: string; format_type: string; reach: number; engagementRate: string; saves: number; timestamp: string }[]
  }
  website: {
    total_sessions: number
    data_window: string
    summary: { health_score: string; top_priority: string }
    top_pages: { path: string; sessions: number; engagement: string }[]
  }
  seo: {
    rising: SeoMove[]
    falling: SeoMove[]
    quick_wins: SeoMove[]
  }
  ab_tests: {
    test_id: string
    hook_or_format: string
    metric: string
    confidence: string
    notes: string
    status: string
  }[]
}

interface SeoMove {
  keyword: string
  previous_rank: number | null
  current_rank: number | null
  search_volume: number
}

interface ExplainItem {
  kind: string
  label?: string
  value?: string
  claim?: string
  action?: string
  next_step?: string
}

const STALE_DAYS = 7

function AsOf({ label, iso }: { label: string; iso?: string }) {
  const age = ageDays(iso)
  return (
    <Badge tone={age !== null && age > STALE_DAYS ? 'red' : 'green'}>
      {label}: {dateOnly(iso) || 'unknown'}
      {age !== null ? ` (${age} days old)` : ''}
    </Badge>
  )
}

function MoveList({ title, rows }: { title: string; rows: SeoMove[] }) {
  return (
    <div>
      <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">{title}</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-sm text-tx3">None.</p>
      ) : (
        <ul className="mt-1 space-y-1 text-sm">
          {rows.map((k) => (
            <li key={k.keyword} className="flex justify-between gap-3 border-t border-white/5 py-1">
              <span className="text-tx">{k.keyword}</span>
              <span className="text-tx3">
                {k.previous_rank ?? '—'} → {k.current_rank ?? '—'} · {k.search_volume || '—'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ReachPage() {
  const { brandId, brandLabel } = useBrand()
  const isSwingShack = brandId === 'swing-shack'
  const [perf, setPerf] = useState<Performance | null>(null)
  const [explain, setExplain] = useState<ExplainItem[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isSwingShack) return
    Promise.all([
      getJson<Performance>('/api/intel/performance'),
      getJson<{ insights: ExplainItem[] }>('/api/intel/explain').catch(() => ({ insights: [] as ExplainItem[] })),
    ])
      .then(([p, e]) => {
        setPerf(p)
        setExplain(e.insights ?? [])
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Reach unavailable'))
  }, [isSwingShack])

  return (
    <div className="space-y-6">
      <PageIntro icon={Activity} badge="Results" here="/results/reach" title="Reach">
        Did anyone see it, and what the numbers say to do next.
      </PageIntro>

      {!isSwingShack ? (
        <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
          <p className="text-sm text-tx2">
            Reach data is only tracked for Swing Shack right now{brandLabel ? `, not ${brandLabel}` : ''}. Switch the brand to Swing Shack to see it.
          </p>
        </section>
      ) : error ? (
        <section className="glass rounded-2xl border-[1.5px] border-red/40 p-5 backdrop-blur-xl">
          <p className="text-sm text-tx2">Could not load reach: {error}</p>
        </section>
      ) : !perf ? (
        <p className="text-sm text-tx3">Loading reach…</p>
      ) : (
        <>
          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <p className="text-sm text-tx2">
              Most of this is older than a week. Check the dates before you act on a number.
            </p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <AsOf label="GA4" iso={perf.data_as_of.ga4} />
              <AsOf label="Instagram" iso={perf.data_as_of.instagram} />
              <AsOf label="SEO audit" iso={perf.data_as_of.seo_audit} />
              <AsOf label="SEO rankings" iso={perf.data_as_of.seo_rankings} />
            </div>
          </section>

          <div className="grid gap-3 sm:grid-cols-4">
            <StatCard icon={Activity} label="GA4 sessions" value={perf.ga4.total_sessions} hint="Latest GA4 pull" tone="mute" />
            <StatCard icon={Activity} label="Instagram posts" value={perf.instagram.total_posts} hint="In the Instagram pull" tone="mute" />
            <StatCard
              icon={Activity}
              label="Website health"
              value={perf.website.summary.health_score}
              hint={perf.website.summary.top_priority}
              tone="mute"
            />
            <StatCard
              icon={Activity}
              label="Website sessions"
              value={perf.website.total_sessions}
              hint={perf.website.data_window}
              tone="mute"
            />
          </div>

          {explain.length > 0 ? (
            <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
              <h2 className="font-display text-lg font-semibold">What the numbers say</h2>
              <ul className="mt-3 space-y-3 text-sm">
                {explain.map((i, idx) => (
                  <li key={`${i.kind}-${idx}`} className="border-t border-white/5 pt-2">
                    <p className="text-tx">{i.claim ?? (i.label ? `${i.label}: ${i.value ?? ''}` : i.kind)}</p>
                    {i.next_step ? <p className="mt-1 text-ac">Next: {i.next_step}</p> : null}
                    {i.action && !i.next_step ? <p className="mt-1 text-ac">{i.action}</p> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">Top pages (GA4)</h2>
            <ul className="mt-2 space-y-1 text-sm">
              {perf.ga4.pages.slice(0, 10).map((p) => (
                <li key={p.path} className="flex justify-between gap-3 border-t border-white/5 py-1">
                  <span className="text-tx">{p.path}</span>
                  <span className="text-tx3">
                    {p.sessions} sessions · {p.engRate} engaged
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">Top Instagram posts</h2>
            <ul className="mt-2 space-y-2 text-sm">
              {perf.instagram.top_posts.slice(0, 10).map((p, i) => (
                <li key={`${p.timestamp}-${i}`} className="border-t border-white/5 pt-2">
                  <p className="text-tx">{p.hook_text}</p>
                  <p className="text-xs text-tx3">
                    {p.format_type} · reach {p.reach} · engagement {p.engagementRate}% · saves {p.saves} ·{' '}
                    {dateOnly(p.timestamp)}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">Search movers (SEO)</h2>
            <div className="mt-2 grid gap-4 sm:grid-cols-3">
              <MoveList title="Rising" rows={perf.seo.rising} />
              <MoveList title="Falling" rows={perf.seo.falling} />
              <MoveList title="Quick wins" rows={perf.seo.quick_wins} />
            </div>
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">A/B tests</h2>
            {perf.ab_tests.length === 0 ? (
              <p className="mt-2 text-sm text-tx3">No tests logged.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-sm">
                {perf.ab_tests.map((t) => (
                  <li key={t.test_id} className="border-t border-white/5 pt-2">
                    <p className="text-tx">
                      {t.hook_or_format} · {t.metric.replaceAll('_', ' ')} · {t.status} · confidence {t.confidence}
                    </p>
                    <p className="text-xs text-tx3">{t.notes}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}
