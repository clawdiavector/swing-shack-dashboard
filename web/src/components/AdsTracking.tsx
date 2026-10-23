import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { Approve } from './AdsApprove'
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
  ids?: { campaign?: string | null; adset?: string | null }
  names?: { ad?: string | null; adset?: string | null; campaign?: string | null }
  current_tags?: string
  tags_fixable?: boolean
  proposal?: { ad_name: string; adset_name: string; campaign_name: string; url_tags: string }
}

type RenamePreview = { object: string; before: string; after: string; ticket: string }
type TagsPreview = { ad_name?: string; before: string; after: string; warning?: string; ticket: string }

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

function Fixes({ brandId, a }: { brandId: string; a: TrackedAd }) {
  const p = a.proposal
  if (!p) return null
  const renames = [
    { object: 'ad', id: a.ad_id, now: a.names?.ad, to: p.ad_name, label: 'Rename ad' },
    { object: 'adset', id: a.ids?.adset, now: a.names?.adset, to: p.adset_name, label: 'Rename ad set' },
    { object: 'campaign', id: a.ids?.campaign, now: a.names?.campaign, to: p.campaign_name, label: 'Rename campaign' },
  ].filter((r) => r.id && r.now !== r.to)
  const needsTags = a.destination === 'WEBSITE' && (a.current_tags ?? '') !== p.url_tags
  const canTag = a.tags_fixable !== false
  if (!renames.length && !needsTags) return <p className="mt-1 text-xs text-ac">Named and tagged to the standard.</p>
  return (
    <div className="mt-2 space-y-2">
      {renames.map((r) => (
        <div key={r.object} className="flex flex-wrap items-center gap-2 text-xs text-tx2">
          <span>
            {r.object}: <span className="text-tx3">{r.now}</span> → <span className="font-semibold text-tx">{r.to}</span>
          </span>
          <Approve<RenamePreview>
            brandId={brandId}
            label={r.label}
            previewPath="rename/preview"
            applyPath="rename"
            body={{ kind: r.object, id: r.id, name: r.to }}
            describe={(pv) => (
              <p>
                Rename the {pv.object} <span className="font-semibold">{pv.before}</span> to{' '}
                <span className="font-semibold">{pv.after}</span>? Renaming does not touch delivery.
              </p>
            )}
            doneText={(pv) => `Renamed to ${pv.after}.`}
          />
        </div>
      ))}
      {needsTags && !canTag ? (
        <p className="text-xs text-tx2">
          UTM tags: this ad uses Meta&apos;s flexible creative, which cannot be tagged from here. Paste the standard tags into its URL
          parameters in Ads Manager when it is next edited or recreated: <span className="break-all text-tx">{p.url_tags}</span>
        </p>
      ) : null}
      {needsTags && canTag ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-tx2">
          <span>
            UTM tags: <span className="text-tx3">{a.current_tags || 'none'}</span> → <span className="break-all font-semibold text-tx">{p.url_tags}</span>
          </span>
          <Approve<TagsPreview>
            brandId={brandId}
            label="Add standard UTM tags"
            previewPath="tags/preview"
            applyPath="tags"
            body={{ ad_id: a.ad_id, url_tags: p.url_tags }}
            describe={(pv) => (
              <p>
                Add these URL parameters to <span className="font-semibold">{pv.ad_name}</span>:{' '}
                <span className="break-all font-semibold">{pv.after}</span>
              </p>
            )}
            warning={(pv) => pv.warning}
            doneText={() => 'UTM tags added.'}
          />
        </div>
      ) : null}
    </div>
  )
}

export function TrackingView({ t, brandId, canChange = false }: { t: Tracking; brandId?: string; canChange?: boolean }) {
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
            {canChange && brandId ? <Fixes brandId={brandId} a={a} /> : null}
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
  const [writes, setWrites] = useState(false)

  useEffect(() => {
    setT(null)
    setError(null)
    getJson<{ tracking: Tracking }>(`/api/meta/ads/${brandId}/tracking`)
      .then((r) => setT(r.tracking))
      .catch((e: Error) => setError(e.message))
    getJson<{ enabled?: boolean }>(`/api/meta/ads/${brandId}/write-status`)
      .then((r) => setWrites(!!r.enabled))
      .catch(() => setWrites(false))
  }, [brandId])

  if (error) return <Note>No tracking check yet ({error}). It is written each day by the ads brief job.</Note>
  if (!t) return <div className="h-24 animate-pulse rounded-2xl bg-bg3" />
  return <TrackingView t={t} brandId={brandId} canChange={writes} />
}
