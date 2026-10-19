import { TrendingUp } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useBrand } from '../../components/BrandSwitch'
import { PageIntro } from '../../components/chrome'
import { getJson } from '../../lib/api'

function Note({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-bd bg-bg2 p-3 text-sm text-tx2">{children}</p>
}

// Meta ads only exist for these two brands (see _ADS_BRIEF_BRANDS in campaign-os/app.py).
const ADS_BRANDS = ['swing-shack', 'stick']

type WeekRow = { week: string; spend: number; leads: number; cost_per_lead: number | null; landing_page_views: number }
type Block = { spend: number; leads: number; cost_per_lead: number | null; landing_page_views: number }
type AdsTrends = {
  weeks: WeekRow[]
  last_4: Block | null
  prior_4: Block | null
  change: Record<string, number | null>
}
type WinnerAd = {
  ad_id: string
  ad_name?: string
  spend: number
  still_running: boolean
  result: { label: string; count: number; cost: number | null; proven: boolean } | null
}
type AdsTrendsResponse = {
  ok: boolean
  trends: AdsTrends
  winners: { ranked?: Record<string, { label: string; ads: WinnerAd[] }> }
  period: { since?: string; until?: string }
  errors: unknown[]
}
type Signal = {
  id: string
  source: string
  title: string
  detail: string
  relevance: number
  suggested_response: string
}
type SignalsResponse = { ok: boolean; signals: Signal[] }

const TILES: { key: keyof Block; label: string; lowerIsBetter?: boolean; money?: boolean }[] = [
  { key: 'spend', label: 'Spend', money: true },
  { key: 'leads', label: 'Leads' },
  { key: 'cost_per_lead', label: 'Cost per lead', lowerIsBetter: true, money: true },
  { key: 'landing_page_views', label: 'Landing page views' },
]

function money(n: number | null | undefined) {
  return n == null ? '—' : `R${Math.round(n).toLocaleString('en-ZA')}`
}

function pct(change: number | null | undefined) {
  if (change == null) return null
  const sign = change > 0 ? '+' : ''
  return `${sign}${Math.round(change * 100)}%`
}

function ChangeBadge({ change, lowerIsBetter }: { change: number | null | undefined; lowerIsBetter?: boolean }) {
  const text = pct(change)
  if (!text || change == null) return <span className="text-xs text-tx2">no change figure</span>
  const good = lowerIsBetter ? change < 0 : change > 0
  const cls = change === 0 ? 'text-tx2' : good ? 'text-green-400' : 'text-red-400'
  return <span className={`text-xs font-semibold ${cls}`}>{text} vs prior 4 weeks</span>
}

function AdsSection({ brandId, brandLabel }: { brandId: string; brandLabel?: string }) {
  const [data, setData] = useState<AdsTrendsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setData(null)
    setError(null)
    getJson<AdsTrendsResponse>(`/api/meta/ads/trends/${brandId}`)
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [brandId])

  if (error) {
    return (
      <Note>
        No ad trends yet for {brandLabel || brandId} ({error}). The ads brief job writes them each day. Run it from
        the Ops page, or ask Kyle to check the job.
      </Note>
    )
  }
  if (!data) return <div className="h-40 animate-pulse rounded-2xl bg-bg3" />

  const { trends, winners, period } = data
  const recentWeeks = (trends.weeks ?? []).slice(-12)
  const maxSpend = Math.max(1, ...recentWeeks.map((w) => w.spend))
  const winnerGroups = Object.values(winners?.ranked ?? {}).filter((g) => g.ads?.length)

  return (
    <div className="space-y-6">
      <p className="text-sm text-tx2">
        Meta ads for {brandLabel || brandId}
        {period.since && period.until ? `, ${period.since} to ${period.until}` : ''}. Last 4 weeks against the 4
        before.
      </p>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {TILES.map((t) => {
          const value = trends.last_4?.[t.key]
          const shown = t.money ? money(value as number | null) : value == null ? '—' : String(value)
          return (
            <div key={t.key} className="rounded-2xl border border-white/10 bg-bg2/80 p-4">
              <p className="text-xs uppercase tracking-wide text-tx2">{t.label}</p>
              <p className="mt-1 text-2xl font-semibold text-tx">{shown}</p>
              <div className="mt-1">
                <ChangeBadge change={trends.change?.[t.key]} lowerIsBetter={t.lowerIsBetter} />
              </div>
            </div>
          )
        })}
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-tx">Spend by week</h3>
        {recentWeeks.length === 0 ? (
          <Note>No weekly data in this period yet.</Note>
        ) : (
          <ul className="space-y-1">
            {recentWeeks.map((w) => (
              <li key={w.week} className="flex items-center gap-3 text-xs">
                <span className="w-20 shrink-0 text-tx2">{w.week}</span>
                <div className="h-3 flex-1 rounded bg-bg3">
                  <div className="h-3 rounded bg-ac" style={{ width: `${(w.spend / maxSpend) * 100}%` }} />
                </div>
                <span className="w-24 shrink-0 text-right text-tx">
                  {money(w.spend)} · {w.leads} leads
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-tx">Ads that worked</h3>
        {winnerGroups.length === 0 ? (
          <Note>No ad has a clear result yet. Ads need a few weeks of delivery before they are ranked.</Note>
        ) : (
          <div className="space-y-4">
            {winnerGroups.map((g) => (
              <div key={g.label}>
                <p className="mb-1 text-xs uppercase tracking-wide text-tx2">Best for {g.label}</p>
                <ul className="space-y-1">
                  {g.ads.map((a) => (
                    <li
                      key={a.ad_id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm"
                    >
                      <span className="text-tx">
                        {a.ad_name || a.ad_id}
                        {a.still_running ? <span className="ml-2 text-xs text-green-400">running</span> : null}
                      </span>
                      <span className="text-xs text-tx2">
                        {a.result
                          ? `${a.result.count} ${a.result.label} · ${money(a.result.cost)} each${a.result.proven ? '' : ' · not proven yet'}`
                          : money(a.spend)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function MarketSection() {
  const [signals, setSignals] = useState<Signal[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getJson<SignalsResponse>('/api/intel/trends_v2')
      .then((d) => setSignals(d.signals || []))
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-semibold text-tx">Market signals</h2>
        <p className="text-sm text-tx2">
          A hand-picked list of marketing and golf news, with a suggested post for each. Nothing refreshes it
          automatically, so check the date before you act on it.
        </p>
      </div>
      {error ? (
        <Note>Could not load market signals ({error}).</Note>
      ) : !signals ? (
        <div className="h-24 animate-pulse rounded-2xl bg-bg3" />
      ) : signals.length === 0 ? (
        <Note>No market signals saved yet.</Note>
      ) : (
        <ul className="space-y-3">
          {signals.map((s) => (
            <li key={s.id} className="rounded-2xl border border-white/10 bg-bg2/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="font-semibold text-tx">{s.title}</p>
                <span className="shrink-0 text-xs text-tx2">relevance {s.relevance}</span>
              </div>
              <p className="mt-1 text-sm text-tx2">{s.detail}</p>
              <p className="mt-2 text-sm text-tx">
                <span className="font-semibold">Try: </span>
                {s.suggested_response}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function Trends() {
  const { brandId, brandLabel } = useBrand()
  const hasAds = !!brandId && ADS_BRANDS.includes(brandId)

  return (
    <div className="space-y-8">
      <PageIntro title="Trends" icon={TrendingUp} here="/results/trends">
        What is moving. Ads first, then the market.
      </PageIntro>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-tx">Paid movement</h2>
        {hasAds && brandId ? (
          <AdsSection brandId={brandId} brandLabel={brandLabel} />
        ) : (
          <Note>Paid trends exist for Swing Shack and Stick only. Switch brand at the top to see them.</Note>
        )}
      </section>

      <MarketSection />
    </div>
  )
}
