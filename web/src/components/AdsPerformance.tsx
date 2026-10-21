import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { rand } from '../lib/rand'
import { Badge } from './ui'
import { Note } from './AdsTrends'
import type { Tracking } from './AdsTracking'

// How each ad performed: Meta's spend and results next to Google Analytics' visits, engagement and key events,
// one card per ad, from the same daily check as "Ad links and tracking". Reading only.

export type Perf = {
  impressions: number
  leads: number
  messages: number
  cost_per_lead: number | null
  cost_per_message: number | null
  cost_per_session: number | null
  engaged_pct: number | null
  click_to_session_pct: number | null
  key_events: number | null
}

type Row = {
  ad_id: string
  ad_name?: string | null
  campaign?: string | null
  destination: string
  spend: number
  link_clicks: number
  ga_sessions: number
  ga_key_events?: number
  perf?: Perf
  proposal?: { ad_name: string }
}

type Totals = {
  spend: number
  leads: number
  messages: number
  cost_per_lead: number | null
  ga_sessions: number
  ga_engaged_pct: number | null
  ga_key_events: number
  cost_per_session: number | null
}

export type PerformanceData = Omit<Tracking, 'ads'> & { ads: Row[]; totals?: Totals }

const pct = (n: number | null | undefined) => (n == null ? '—' : `${n}%`)
const num = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('en-ZA'))

/** A plain-words reading of one ad, or null when there is nothing fair to say yet. */
export function verdict(r: Row, brandCostPerLead: number | null): { text: string; tone: 'green' | 'red' | 'gold' } | null {
  const p = r.perf
  if (!p) return null
  if (p.cost_per_lead != null && brandCostPerLead != null && p.leads >= 5) {
    return p.cost_per_lead <= brandCostPerLead
      ? { text: `Cheaper than the brand's average lead (${rand(brandCostPerLead)}).`, tone: 'green' }
      : { text: `Dearer than the brand's average lead (${rand(brandCostPerLead)}).`, tone: 'red' }
  }
  if (p.engaged_pct != null && r.ga_sessions >= 50 && p.engaged_pct < 30) {
    return { text: `Only ${p.engaged_pct}% of visitors stayed and engaged. The page it lands on is the likely problem.`, tone: 'red' }
  }
  if (p.engaged_pct != null && r.ga_sessions >= 50 && p.engaged_pct >= 55) {
    return { text: `${p.engaged_pct}% of visitors engaged: the page holds people.`, tone: 'green' }
  }
  if (p.key_events === 0 && r.ga_sessions >= 50) {
    return { text: 'No enquiry (call, email or contact) recorded from these visits yet. Counting only started on 21 Oct.', tone: 'gold' }
  }
  return null
}

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-tx3">{label}</p>
      <p className="text-sm font-semibold text-tx">{value}</p>
      {sub ? <p className="text-[11px] text-tx3">{sub}</p> : null}
    </div>
  )
}

export function PerformanceView({ t }: { t: PerformanceData }) {
  const tot = t.totals
  const rows = t.ads
  if (!rows.length) return <Note>No ad delivered in the last 31 days.</Note>
  return (
    <div className="space-y-3">
      {tot ? (
        <p className="text-sm text-tx2">
          Spent {rand(tot.spend)} in 31 days.
          {tot.leads ? ` ${tot.leads} leads at ${rand(tot.cost_per_lead)} each.` : ''}
          {tot.messages ? ` ${tot.messages} chats.` : ''}
          {tot.ga_sessions
            ? ` On the website (Google Analytics, 28 days): ${num(tot.ga_sessions)} visits at ${rand(tot.cost_per_session)} each, ${pct(tot.ga_engaged_pct)} engaged, ${tot.ga_key_events} enquiries recorded.`
            : ''}
        </p>
      ) : null}
      <ul className="space-y-2">
        {rows.map((r) => {
          const p = r.perf
          const v = verdict(r, tot?.cost_per_lead ?? null)
          const onSite = p?.cost_per_session != null
          return (
            <li key={r.ad_id} className="rounded-xl border border-white/10 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-tx">{r.ad_name ?? r.ad_id}</span>
                <Badge tone={onSite ? 'blue' : 'mute'}>{r.destination === 'WEBSITE' ? 'Website' : r.destination === 'LEAD_FORM' ? 'Lead form' : r.destination === 'MESSAGING' ? 'Messages' : 'Unknown'}</Badge>
              </div>
              <p className="text-xs text-tx3">{r.campaign}</p>
              <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Cell label="Spent" value={rand(r.spend)} sub={`${num(r.link_clicks)} link clicks`} />
                {p && r.destination === 'LEAD_FORM' && p.leads ? (
                  <Cell label="Leads" value={String(p.leads)} sub={`${rand(p.cost_per_lead)} each`} />
                ) : p && r.destination === 'MESSAGING' && p.messages ? (
                  <Cell label="Chats" value={String(p.messages)} sub={`${rand(p.cost_per_message)} each`} />
                ) : (
                  <Cell label="Visits (GA4)" value={onSite ? num(r.ga_sessions) : '—'} sub={onSite ? `${rand(p?.cost_per_session)} each` : 'not on the website'} />
                )}
                <Cell label="Engaged" value={pct(p?.engaged_pct)} sub={onSite ? 'of visitors' : undefined} />
                <Cell label="Enquiries" value={p?.key_events == null ? '—' : String(p.key_events)} sub={onSite ? 'call, email, contact' : undefined} />
                <Cell label="Clicks that arrived" value={pct(p?.click_to_session_pct)} sub={onSite ? 'of Meta link clicks' : undefined} />
              </div>
              {v ? (
                <p className={`mt-2 text-xs font-semibold ${v.tone === 'green' ? 'text-ac' : v.tone === 'red' ? 'text-red' : 'text-yel'}`}>{v.text}</p>
              ) : null}
            </li>
          )
        })}
      </ul>
      <p className="text-xs text-tx3">
        Meta numbers cover the last 31 days, Google Analytics the last 28. Enquiries count calls, emails and contact clicks marked in
        Google Analytics on 21 Oct, so they start low.
      </p>
    </div>
  )
}

export function AdsPerformance({ brandId }: { brandId: string }) {
  const [t, setT] = useState<PerformanceData | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setT(null)
    setError(null)
    getJson<{ tracking: PerformanceData }>(`/api/meta/ads/${brandId}/tracking`)
      .then((r) => setT(r.tracking))
      .catch((e: Error) => setError(e.message))
  }, [brandId])
  if (error) return <Note>No performance check yet ({error}). It is written each day by the ads brief job.</Note>
  if (!t) return <div className="h-24 animate-pulse rounded-2xl bg-bg3" />
  return <PerformanceView t={t} />
}
