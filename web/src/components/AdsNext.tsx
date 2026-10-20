import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { Note } from './AdsTrends'
import { SetDecisionDate } from './AdsDecisionDate'
import { PauseAd } from './AdsPause'
import { Badge } from './ui'

// "What to do next" for the Trends page: the top actions from the daily ads brief
// (GET /api/meta/ads/brief/<brand>). Recommendations only; nothing here changes an ad.

type TopAction = {
  action: string
  why?: string
  status?: string
  severity?: string
  days_open?: number
  rule?: string
  ads?: string[]
  ad_ids?: string[]
}

type OpenItem = {
  rule?: string
  action: string
  status?: string
  severity?: string
  ad_id?: string
  ad_name?: string
  days_open?: number
  what?: string
}

export type Brief = {
  date?: string
  note?: string
  headline?: { actions?: number; new?: number; open?: number; resolved?: number }
  top_actions?: TopAction[]
  open?: OpenItem[] | number
}

const SEVERITY_TONE: Record<string, 'red' | 'gold' | 'mute'> = { high: 'red', medium: 'gold' }

export function AdsNext({ brandId }: { brandId: string }) {
  const [brief, setBrief] = useState<Brief | null>(null)
  const [writes, setWrites] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setBrief(null)
    setError(null)
    getJson<{ brief?: Brief }>(`/api/meta/ads/brief/${brandId}`)
      .then((r) => setBrief(r.brief ?? {}))
      .catch((e: Error) => setError(e.message))
    getJson<{ enabled?: boolean }>(`/api/meta/ads/${brandId}/write-status`)
      .then((r) => setWrites(!!r.enabled))
      .catch(() => setWrites(false))
  }, [brandId])

  if (error) return <Note>No ads brief yet ({error}). It is written each day by the ads brief job.</Note>
  if (!brief) return <div className="h-24 animate-pulse rounded-2xl bg-bg3" />
  return <AdsNextView brief={brief} brandId={brandId} canChange={writes} />
}

export function AdsNextView({
  brief,
  brandId,
  canChange = false,
}: {
  brief: Brief
  brandId?: string
  canChange?: boolean
}) {
  const actions = brief.top_actions ?? []
  // Open items the top three do not already name (same rule and status), so nothing is listed twice.
  const shown = new Set(actions.map((a) => `${a.rule}|${a.status ?? ''}`))
  const others = (Array.isArray(brief.open) ? brief.open : []).filter((o) => !shown.has(`${o.rule}|${o.status ?? ''}`))
  const h = brief.headline

  return (
    <div className="space-y-3">
      <p className="text-sm text-tx2">
        {h ? `${h.open ?? 0} open, ${h.new ?? 0} new, ${h.resolved ?? 0} resolved` : 'Latest ads brief'}
        {brief.date ? ` · brief of ${brief.date}` : ''}. {brief.note ?? 'Recommendations only. Nothing here changes an ad.'}
      </p>
      {actions.length === 0 ? (
        <Note>Nothing needs doing on the ads right now.</Note>
      ) : (
        <ul className="space-y-2">
          {actions.map((a, i) => (
            <li key={`${a.rule ?? 'a'}-${i}`} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-tx">{a.action}</span>
                {a.severity ? <Badge tone={SEVERITY_TONE[a.severity] ?? 'mute'}>{a.severity}</Badge> : null}
              </div>
              {a.why ? <p className="mt-1 text-tx2">{a.why}</p> : null}
              {a.days_open ? <p className="mt-1 text-xs text-tx3">open {a.days_open} days</p> : null}
              {canChange && brandId && a.ad_ids?.length ? (
                <ul className="mt-2 space-y-2">
                  {a.ad_ids.map((id, j) => (
                    <li key={id} className="flex flex-wrap items-center gap-2 text-xs text-tx2">
                      <span>{a.ads?.[j] ?? id}</span>
                      {a.status === 'DECISION_DATE' ? (
                        <SetDecisionDate brandId={brandId} adId={id} adName={a.ads?.[j] ?? id} />
                      ) : null}
                      <PauseAd brandId={brandId} adId={id} adName={a.ads?.[j] ?? id} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {others.length > 0 ? (
        <details className="rounded-xl border border-white/10 px-3 py-2 text-sm">
          <summary className="cursor-pointer font-semibold text-tx">More open items ({others.length})</summary>
          <ul className="mt-2 space-y-2">
            {others.map((o, i) => (
              <li key={`${o.ad_id ?? o.ad_name ?? 'o'}-${i}`} className="border-t border-white/5 pt-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-tx">{o.action}</span>
                  {o.severity ? <Badge tone={SEVERITY_TONE[o.severity] ?? 'mute'}>{o.severity}</Badge> : null}
                </div>
                {o.ad_name ? <p className="text-xs text-tx2">{o.ad_name}</p> : null}
                {o.what ? <p className="text-xs text-tx3">{o.what}</p> : null}
                {canChange && brandId && o.ad_id ? (
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {o.status === 'DECISION_DATE' ? (
                      <SetDecisionDate brandId={brandId} adId={o.ad_id} adName={o.ad_name ?? o.ad_id} />
                    ) : null}
                    <PauseAd brandId={brandId} adId={o.ad_id} adName={o.ad_name ?? o.ad_id} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {/* A server-rendered page outside the SPA, so a plain link, not a router Link. */}
      <a href="/ads-brief" className="inline-block text-sm font-semibold text-ac hover:underline">
        See the full ads brief
      </a>
    </div>
  )
}
