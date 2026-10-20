import { useEffect, useState } from 'react'
import { getJson } from '../lib/api'
import { Note } from './AdsTrends'
import { Badge } from './ui'

// The Moments desk: dates to plan around, and what South Africa is talking about today.
// Read only (GET /api/moments). Starter lines are templates to edit; nothing posts from here.

type Upcoming = {
  date: string
  end?: string | null
  title: string
  angle?: string
  days_to: number
  prep_by: string
  status: 'on now' | 'prepare now' | 'coming'
}

type LiveItem = {
  title: string
  source: string
  link?: string | null
  category: string
  traffic?: string | null
  age_hours?: number | null
  act_today: boolean
  why: string
  starter_line: string
}

export type MomentsData = {
  generated_at?: string
  upcoming?: Upcoming[]
  live?: LiveItem[]
  hidden_sensitive?: number
  errors?: string[]
}

// The templates end with the brand's name. With no brand picked, drop the sign-off rather than write "us".
export function fillStarter(line: string, brandLabel?: string) {
  return brandLabel ? line.replace('{brand}', brandLabel) : line.replace(' {brand}.', '')
}

export function ageLabel(h?: number | null) {
  if (h == null) return ''
  if (h < 1) return 'just now'
  if (h < 24) return `${Math.round(h)}h ago`
  return `${Math.round(h / 24)}d ago`
}

export function Moments({ brandLabel }: { brandLabel?: string }) {
  const [data, setData] = useState<MomentsData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getJson<{ moments?: MomentsData }>('/api/moments')
      .then((r) => setData(r.moments ?? {}))
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <Note>Moments are not available right now ({error}).</Note>
  if (!data) return <div className="h-32 animate-pulse rounded-2xl bg-bg3" />
  return <MomentsView data={data} brandLabel={brandLabel} />
}

export function MomentsView({ data, brandLabel }: { data: MomentsData; brandLabel?: string }) {
  const upcoming = data.upcoming ?? []
  const live = data.live ?? []

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-2 text-sm font-semibold text-tx">Coming up</h3>
        {upcoming.length === 0 ? (
          <Note>Nothing on the calendar in the next 60 days.</Note>
        ) : (
          <ul className="space-y-2">
            {upcoming.map((u) => (
              <li key={`${u.date}-${u.title}`} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-tx">{u.title}</span>
                  <Badge tone={u.status === 'prepare now' ? 'red' : 'mute'}>{u.status}</Badge>
                  <span className="text-xs text-tx3">
                    {u.date}
                    {u.end ? ` to ${u.end}` : ''} · {u.days_to === 0 ? 'now' : `in ${u.days_to} days`} · prepare by{' '}
                    {u.prep_by}
                  </span>
                </div>
                {u.angle ? <p className="mt-1 text-tx2">{u.angle}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-tx">Happening now in South Africa</h3>
        {live.length === 0 ? (
          <Note>Nothing with a golf or sport angle in the news right now.</Note>
        ) : (
          <ul className="space-y-3">
            {live.map((l) => (
              <li key={`${l.source}-${l.title}`} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-tx">{l.title}</span>
                  {l.act_today ? <Badge tone="red">act today</Badge> : null}
                </div>
                <p className="mt-1 text-xs text-tx3">
                  {l.source}
                  {l.traffic ? ` · ${l.traffic} searches` : ''}
                  {l.age_hours != null ? ` · ${ageLabel(l.age_hours)}` : ''}
                </p>
                <p className="mt-1 text-tx2">{l.why}</p>
                <p className="mt-1 text-ac">
                  Starter line, edit before use: {fillStarter(l.starter_line, brandLabel)}
                </p>
                {l.link ? (
                  <a
                    href={l.link}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-xs text-tx2 hover:text-ac"
                  >
                    Read the story
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {data.hidden_sensitive ? (
          <p className="mt-2 text-xs text-tx3">
            {data.hidden_sensitive} headline{data.hidden_sensitive === 1 ? '' : 's'} hidden as too sensitive to join in
            on.
          </p>
        ) : null}
        {data.errors?.length ? (
          <p className="mt-1 text-xs text-tx3">Some sources did not load: {data.errors.join(', ')}.</p>
        ) : null}
      </section>
    </div>
  )
}
