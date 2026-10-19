import { TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { ADS_BRANDS, AdsSection, Note } from '../components/AdsTrends'
import { PageIntro } from '../components/chrome'
import { Badge } from '../components/ui'
import { getJson } from '../lib/api'
import { ageDays, dateOnly } from '../lib/dataAge'

// Native Trends page. Reads the two endpoints the classic Trends view used:
// GET /api/intel/trend_catcher (YouTube, Reddit, golf news, competitor changes)
// GET /api/intel/trends_v2     (ranked signals with suggested responses)

interface YouTubeItem {
  title: string
  channelTitle: string
  publishedAt: string
  videoId: string
  query: string
}

interface CompetitorChange {
  competitor: string
  date: string
  what_changed: string
  threat_level: string
  opportunity_level: string
  response: string
}

interface TrendCatcher {
  summary: string
  data_as_of: Record<string, string>
  youtube: YouTubeItem[]
  reddit: unknown[]
  golf_news: unknown[]
  competitor_changes: CompetitorChange[]
}

interface Signal {
  id: string
  title: string
  detail: string
  suggested_response: string
  relevance: number
  source: string
  freshness: string
}

interface TrendsV2 {
  count: number
  signals: Signal[]
  sources: string[]
}

const STALE_DAYS = 7

// YouTube titles arrive HTML-escaped (&#39;, &amp;). DOMParser decodes them without running any script.
function decodeEntities(text: string): string {
  return new DOMParser().parseFromString(text, 'text/html').documentElement.textContent ?? text
}

function AsOf({ label, iso }: { label: string; iso?: string }) {
  const age = ageDays(iso)
  return (
    <Badge tone={age !== null && age > STALE_DAYS ? 'red' : 'green'}>
      {label}: {dateOnly(iso) || 'unknown'}
      {age !== null ? ` (${age} days old)` : ''}
    </Badge>
  )
}

export function TrendsPage() {
  const { brandId, brandLabel } = useBrand()
  const isSwingShack = brandId === 'swing-shack'
  const hasAds = !!brandId && ADS_BRANDS.includes(brandId)
  const [catcher, setCatcher] = useState<TrendCatcher | null>(null)
  const [signals, setSignals] = useState<TrendsV2 | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isSwingShack) return
    Promise.all([
      getJson<TrendCatcher>('/api/intel/trend_catcher'),
      getJson<TrendsV2>('/api/intel/trends_v2'),
    ])
      .then(([c, s]) => {
        setCatcher(c)
        setSignals(s)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Trends unavailable'))
  }, [isSwingShack])

  const topSignals = [...(signals?.signals ?? [])].sort((a, b) => b.relevance - a.relevance).slice(0, 10)

  return (
    <div className="space-y-6">
      <PageIntro icon={TrendingUp} badge="Results" here="/results/trends" title="Trends">
        What is moving: ads first, then golf and the competitor set, and what to do about it.
      </PageIntro>

      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold">Paid movement</h2>
        {hasAds && brandId ? (
          <AdsSection brandId={brandId} brandLabel={brandLabel} />
        ) : (
          <Note>Paid trends exist for Swing Shack and Stick only. Switch brand at the top to see them.</Note>
        )}
      </section>

      {!isSwingShack ? (
        <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
          <p className="text-sm text-tx2">
            Trends data is only tracked for Swing Shack right now{brandLabel ? `, not ${brandLabel}` : ''}. Switch the brand to Swing Shack to see it.
          </p>
        </section>
      ) : error ? (
        <section className="glass rounded-2xl border-[1.5px] border-red/40 p-5 backdrop-blur-xl">
          <p className="text-sm text-tx2">Could not load trends: {error}</p>
        </section>
      ) : !catcher || !signals ? (
        <p className="text-sm text-tx3">Loading trends…</p>
      ) : (
        <>
          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <p className="text-sm text-tx2">{catcher.summary}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              {Object.entries(catcher.data_as_of).map(([source, iso]) => (
                <AsOf key={source} label={source} iso={iso} />
              ))}
            </div>
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">
              Signals to act on <span className="text-sm text-tx3">({signals.count})</span>
            </h2>
            {topSignals.length === 0 ? (
              <p className="mt-2 text-sm text-tx3">No signals right now.</p>
            ) : (
              <ul className="mt-3 space-y-4">
                {topSignals.map((s) => (
                  <li key={s.id} className="border-t border-white/5 pt-3">
                    <p className="font-semibold text-tx">{s.title}</p>
                    <p className="mt-1 text-sm text-tx2">{s.detail}</p>
                    <p className="mt-1 text-sm text-ac">Respond: {s.suggested_response}</p>
                    <p className="mt-1 text-xs text-tx3">
                      {s.source} · relevance {s.relevance} · {s.freshness}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">Competitors</h2>
            {catcher.competitor_changes.length === 0 ? (
              <p className="mt-2 text-sm text-tx3">No competitor changes logged.</p>
            ) : (
              <ul className="mt-2 space-y-3 text-sm">
                {catcher.competitor_changes.map((c, i) => (
                  <li key={`${c.competitor}-${i}`} className="border-t border-white/5 pt-2">
                    <p className="text-tx">
                      <span className="font-semibold">{c.competitor}</span> · {c.what_changed.replaceAll('_', ' ')} ·{' '}
                      <span className="text-tx3">{dateOnly(c.date)}</span>
                    </p>
                    <p className="mt-1 text-tx2">{c.response}</p>
                    <p className="mt-1 text-xs text-tx3">
                      threat {c.threat_level} · opportunity {c.opportunity_level}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">YouTube</h2>
            {catcher.youtube.length === 0 ? (
              <p className="mt-2 text-sm text-tx3">Nothing pulled.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-sm">
                {catcher.youtube.slice(0, 10).map((v) => (
                  <li key={v.videoId} className="border-t border-white/5 pt-2">
                    <a
                      href={`https://www.youtube.com/watch?v=${encodeURIComponent(v.videoId)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-tx hover:text-ac"
                    >
                      {decodeEntities(v.title)}
                    </a>
                    <p className="text-xs text-tx3">
                      {v.channelTitle} · {dateOnly(v.publishedAt)} · search “{v.query}”
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">Reddit and golf news</h2>
            <p className="mt-2 text-sm text-tx3">
              Reddit: {catcher.reddit.length} threads. Golf news: {catcher.golf_news.length} items.
            </p>
          </section>
        </>
      )}
    </div>
  )
}
