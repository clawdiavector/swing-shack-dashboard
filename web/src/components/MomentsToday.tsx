import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getJson } from '../lib/api'
import { Badge } from './ui'
import { ageLabel, fillStarter, type MomentsData } from './Moments'

// The morning alert, on the page you open first: only the Moments marked "act today", and
// dates that need preparing now. Shows nothing at all on a quiet day. Read only; nothing posts.

const MAX_ITEMS = 3

export function MomentsToday({ brandLabel }: { brandLabel?: string }) {
  const [data, setData] = useState<MomentsData | null>(null)

  useEffect(() => {
    // A quiet or failed read just means no card: this is an alert, not a page.
    getJson<{ moments?: MomentsData }>('/api/moments')
      .then((r) => setData(r.moments ?? null))
      .catch(() => setData(null))
  }, [])

  return data ? <MomentsTodayView data={data} brandLabel={brandLabel} /> : null
}

export function MomentsTodayView({ data, brandLabel }: { data: MomentsData; brandLabel?: string }) {
  const hot = (data.live ?? []).filter((l) => l.act_today).slice(0, MAX_ITEMS)
  const prep = (data.upcoming ?? []).filter((u) => u.status === 'prepare now')
  if (hot.length === 0 && prep.length === 0) return null

  return (
    <section
      aria-label="Moments to join today"
      className="glass rounded-2xl border-[1.5px] border-yel/40 p-4 backdrop-blur-xl"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold">Worth joining today</h2>
        <Link to="/results/trends" className="text-sm font-semibold text-ac hover:underline">
          See all Moments
        </Link>
      </div>
      {hot.length > 0 ? (
        <ul className="mt-3 space-y-3 text-sm">
          {hot.map((l) => (
            <li key={`${l.source}-${l.title}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-tx">{l.title}</span>
                <Badge tone="red">act today</Badge>
                {l.age_hours != null ? <span className="text-xs text-tx3">{ageLabel(l.age_hours)}</span> : null}
              </div>
              <p className="mt-1 text-tx2">{l.why}</p>
              <p className="mt-1 text-ac">Starter line, edit before use: {fillStarter(l.starter_line, brandLabel)}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {prep.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm text-tx2">
          {prep.map((u) => (
            <li key={`${u.date}-${u.title}`}>
              <span className="font-semibold text-tx">{u.title}</span> is on {u.date}. Prepare it now.
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
