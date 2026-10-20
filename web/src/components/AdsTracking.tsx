import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { Note } from './AdsTrends'
import { Badge } from './ui'

// Ad links and tracking: per running ad, where the button goes, what its UTMs say, and what Google Analytics
// saw. GET /api/meta/ads/<brand>/tracking (from the daily ads brief job). Reading only.

type TrackedAd = {
  ad_id: string
  ad_name?: string
  campaign?: string
  destination: 'WEBSITE' | 'LEAD_FORM' | 'MESSAGING' | 'UNKNOWN'
  host?: string | null
  utm: Record<string, string | null>
  issues: string[]
  notes: string[]
  ga_sessions: number
  spend: number
  link_clicks: number
}

export type Tracking = {
  date?: string
  summary: {
    running_ads: number
    website_ads: number
    website_with_complete_utm: number
    website_with_problems: number
    never_reach_site: number
    unknown_destination: number
    ga_paid_sessions: number | null
    ga_matched: number | null
  }
  ads: TrackedAd[]
  errors: string[]
}

const ISSUE: Record<string, string> = {
  NO_UTM: 'no UTM tags',
  INCOMPLETE_UTM: 'UTM missing source, medium or campaign',
  URL_IN_TAGS: 'a whole URL was pasted into the tags',
  PLACEHOLDER_LITERAL: 'a placeholder was typed as text, not filled in',
  EMPTY_VALUE: 'a UTM value is empty',
}
const WHERE: Record<TrackedAd['destination'], string> = {
  WEBSITE: 'Website',
  LEAD_FORM: 'Lead form',
  MESSAGING: 'Messages',
  UNKNOWN: 'Unknown',
}

export function TrackingView({ t }: { t: Tracking }) {
  const s = t.summary
  return (
    <div className="space-y-3">
      <p className="text-sm text-tx2">
        {s.running_ads} running ads: {s.website_ads} send people to the website ({s.website_with_complete_utm} with
        complete UTM tags, {s.website_with_problems} with a problem), {s.never_reach_site} never reach the site (lead
        forms and messages, measured in Meta), {s.unknown_destination} destination unknown.
        {s.ga_paid_sessions != null
          ? ` Google Analytics saw ${s.ga_paid_sessions} paid sessions in 28 days; ${s.ga_matched ?? 0} match a current ad.`
          : ''}
      </p>
      <ul className="space-y-2">
        {t.ads.map((a) => (
          <li key={a.ad_id} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-tx">{a.ad_name ?? a.ad_id}</span>
              <Badge tone={a.destination === 'WEBSITE' ? 'blue' : 'mute'}>{WHERE[a.destination]}</Badge>
              {a.destination === 'WEBSITE' ? (
                a.issues.length ? (
                  <Badge tone="red">Fix tags</Badge>
                ) : (
                  <Badge tone="green">Tags ok</Badge>
                )
              ) : null}
            </div>
            <p className="text-xs text-tx3">
              {a.campaign} · {a.host ?? 'no website'} · Meta link clicks {a.link_clicks}
              {a.destination === 'WEBSITE' ? ` · GA4 sessions ${a.ga_sessions}` : ''}
            </p>
            {a.issues.length ? (
              <p className="text-xs text-red">{a.issues.map((i) => ISSUE[i] ?? i).join('; ')}</p>
            ) : null}
            {a.notes.map((n) => (
              <p key={n} className="text-xs text-tx2">
                {n}
              </p>
            ))}
          </li>
        ))}
      </ul>
      {t.errors.length ? <p className="text-xs text-tx3">Could not read everything: {t.errors.join(' · ')}</p> : null}
    </div>
  )
}

export function AdsTracking({ brandId }: { brandId: string }) {
  const [t, setT] = useState<Tracking | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setT(null)
    setError(null)
    getJson<{ tracking: Tracking }>(`/api/meta/ads/${brandId}/tracking`)
      .then((r) => setT(r.tracking))
      .catch((e: Error) => setError(e.message))
  }, [brandId])

  if (error) return <Note>No tracking check yet ({error}). It is written each day by the ads brief job.</Note>
  if (!t) return <div className="h-24 animate-pulse rounded-2xl bg-bg3" />
  return <TrackingView t={t} />
}
