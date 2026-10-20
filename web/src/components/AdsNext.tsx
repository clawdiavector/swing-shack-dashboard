import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { Note } from './AdsTrends'
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
}

export type Brief = {
  date?: string
  note?: string
  headline?: { actions?: number; new?: number; open?: number; resolved?: number }
  top_actions?: TopAction[]
}

const SEVERITY_TONE: Record<string, 'red' | 'gold' | 'mute'> = { high: 'red', medium: 'gold' }

export function AdsNext({ brandId }: { brandId: string }) {
  const [brief, setBrief] = useState<Brief | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setBrief(null)
    setError(null)
    getJson<{ brief?: Brief }>(`/api/meta/ads/brief/${brandId}`)
      .then((r) => setBrief(r.brief ?? {}))
      .catch((e: Error) => setError(e.message))
  }, [brandId])

  if (error) return <Note>No ads brief yet ({error}). It is written each day by the ads brief job.</Note>
  if (!brief) return <div className="h-24 animate-pulse rounded-2xl bg-bg3" />
  return <AdsNextView brief={brief} />
}

export function AdsNextView({ brief }: { brief: Brief }) {
  const actions = brief.top_actions ?? []
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
            </li>
          ))}
        </ul>
      )}
      {/* A server-rendered page outside the SPA, so a plain link, not a router Link. */}
      <a href="/ads-brief" className="inline-block text-sm font-semibold text-ac hover:underline">
        See the full ads brief
      </a>
    </div>
  )
}
