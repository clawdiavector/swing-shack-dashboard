import { Activity, RefreshCw, Search } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge, StatCard } from '../components/ui'
import { getJson } from '../lib/api'
import { fixLabel, groupFixes, type SeoFix, type SeoFixQueue } from '../lib/seoFixQueue'
import { canUndo, modeNote, statusLabel, type MetaChange, type PublishMode } from '../lib/seoMetaPublish'

// Shape of GET /api/seo/insights (campaign-os/app.py seo_insights_full).
// The endpoint has no brand parameter and reads swingshack.co.za data only,
// so this page shows it for Swing Shack and nothing else.

interface SeoKeyword {
  keyword: string
  current_position: number | null
  previous_position: number | null
  delta?: number | null
  volume: number
  url: string | null
  seo_difficulty: number | null
  opportunity_label: string
}

interface SeoCompetitor {
  domain: string | null
  domain_authority: number | null
  common_keywords: number | null
}

interface SeoInsights {
  domain: string
  domain_health: {
    domain_authority: number
    total_backlinks: number
    ref_domains: number
    keyword_footprint: { tracked: number; top_3: number; top_10: number; ranking_top_100: number; not_ranking: number }
    weekly_change: { up: number; down: number; unchanged: number }
    manager_read: string
  }
  freshness: Record<string, { exists: boolean; age_days: number | null; fresh?: boolean }>
  winning: SeoKeyword[]
  leaking: SeoKeyword[]
  missing: SeoKeyword[]
  quick_wins: SeoKeyword[]
  competitors: SeoCompetitor[]
  summary: { winning_count: number; leaking_count: number; missing_count: number; quick_win_count: number; competitor_count: number }
  metadata: { fetched_at: string | null }
}

const ROWS = 20

// Age in days of the stalest data file, or null when nothing reports an age.
function oldestAge(data: SeoInsights): number | null {
  const ages = Object.values(data.freshness)
    .map((f) => f.age_days)
    .filter((a): a is number => typeof a === 'number')
  return ages.length ? Math.max(...ages) : null
}

function KeywordTable({ title, read, rows }: { title: string; read: string; rows: SeoKeyword[] }) {
  return (
    <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
      <h2 className="font-display text-lg font-semibold">
        {title} <span className="text-sm text-tx3">({rows.length})</span>
      </h2>
      <p className="mt-1 text-sm text-tx3">{read}</p>
      {rows.length === 0 ? (
        <p className="mt-4 text-sm text-tx3">Nothing here this period.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-tx3 uppercase">
              <tr>
                <th className="py-1 pr-3">Keyword</th>
                <th className="py-1 pr-3">Position</th>
                <th className="py-1 pr-3">Was</th>
                <th className="py-1 pr-3">Volume</th>
                <th className="py-1 pr-3">Difficulty</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, ROWS).map((k) => (
                <tr key={`${k.keyword}-${k.opportunity_label}`} className="border-t border-white/5">
                  <td className="py-1.5 pr-3 text-tx">{k.keyword}</td>
                  <td className="py-1.5 pr-3">{k.current_position ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-tx3">{k.previous_position ?? '—'}</td>
                  <td className="py-1.5 pr-3">{k.volume || '—'}</td>
                  <td className="py-1.5 pr-3">{k.seo_difficulty ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > ROWS ? (
            <p className="mt-2 text-xs text-tx3">Showing {ROWS} of {rows.length}.</p>
          ) : null}
        </div>
      )}
    </section>
  )
}

const SEVERITY_TONE = { high: 'red', medium: 'gold', low: 'mute' } as const

function FixRow({ fix }: { fix: SeoFix }) {
  const tone = SEVERITY_TONE[fix.severity ?? 'low'] ?? 'mute'
  return (
    <li className="border-t border-white/5 py-2 text-sm first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone}>{fix.severity ?? 'note'}</Badge>
        <span className="font-semibold text-tx">{fixLabel(fix.type)}</span>
        {fix.page ? <span className="text-tx3">on {fix.page}</span> : null}
      </div>
      {fix.message ? <p className="mt-1 text-tx2">{fix.message}</p> : null}
      {fix.fix ? <p className="mt-1 text-tx3">Suggested fix: {fix.fix}</p> : null}
    </li>
  )
}

// Findings from the daily site check, waiting for a fix. Read-only: nothing
// here changes the website.
function FixesWaiting({ queue }: { queue: SeoFixQueue | null }) {
  const { auto, ask } = groupFixes(queue)
  const total = auto.length + ask.length
  return (
    <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
      <h2 className="font-display text-lg font-semibold">
        Fixes waiting <span className="text-sm text-tx3">({total})</span>
      </h2>
      <p className="mt-1 text-sm text-tx3">
        Found by the daily check of the Swing Shack website. Nothing is changed on the site from this page.
      </p>
      {!queue ? (
        <p className="mt-4 text-sm text-tx3">No check has run yet. The first list appears after tonight's check.</p>
      ) : total === 0 ? (
        <p className="mt-4 text-sm text-tx3">Nothing waiting. The last check found nothing to fix.</p>
      ) : (
        <div className="mt-3 space-y-4">
          {ask.length > 0 ? (
            <div>
              <h3 className="text-xs font-semibold text-tx3 uppercase">Needs your OK before it changes ({ask.length})</h3>
              <ul className="mt-1">
                {ask.map((f) => (
                  <FixRow key={f.id} fix={f} />
                ))}
              </ul>
            </div>
          ) : null}
          {auto.length > 0 ? (
            <div>
              <h3 className="text-xs font-semibold text-tx3 uppercase">
                Can be fixed automatically, with an undo ({auto.length})
              </h3>
              <ul className="mt-1">
                {auto.map((f) => (
                  <FixRow key={f.id} fix={f} />
                ))}
              </ul>
            </div>
          ) : null}
          <p className="text-xs text-tx3">Last checked {queue.updated.slice(0, 10)}.</p>
        </div>
      )}
    </section>
  )
}

const CHANGE_TONE = { applied: 'green', dry_run: 'blue', undone: 'mute', failed: 'red' } as const

// Search descriptions the system wrote (or, in practice mode, would write), each with an undo.
function AutoChanges() {
  const [mode, setMode] = useState<PublishMode>('off')
  const [entries, setEntries] = useState<MetaChange[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const load = useCallback(() => {
    return getJson<{ ok: boolean; mode?: PublishMode; entries?: MetaChange[] }>('/api/seo/meta-publish?brand=swing-shack')
      .then((r) => {
        if (r.ok) {
          setMode(r.mode ?? 'off')
          setEntries(r.entries ?? [])
        }
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function undo(id: string) {
    setBusy(id)
    setNote(null)
    try {
      // Read the body on errors too: the reason (for example "edited since") is in it.
      const res = await fetch('/api/seo/meta-publish/undo', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand: 'swing-shack', id }),
      })
      const r = (await res.json().catch(() => ({ ok: false }))) as { ok: boolean; error?: string }
      setNote(r.ok ? { ok: true, text: 'Put back the way it was.' } : { ok: false, text: r.error || 'Could not undo' })
      await load()
    } catch (e: unknown) {
      setNote({ ok: false, text: e instanceof Error ? e.message : 'Could not undo' })
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
      <h2 className="font-display text-lg font-semibold">
        Changed automatically <span className="text-sm text-tx3">({entries.length})</span>
      </h2>
      <p className="mt-1 text-sm text-tx3">{modeNote(mode)}</p>
      {entries.length === 0 ? (
        <p className="mt-4 text-sm text-tx3">Nothing yet.</p>
      ) : (
        <ul className="mt-3">
          {entries.map((c) => (
            <li key={c.id} className="border-t border-white/5 py-2 text-sm first:border-t-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={CHANGE_TONE[c.status] ?? 'mute'}>{statusLabel(c)}</Badge>
                <span className="font-semibold text-tx">Search description on {c.page}</span>
                <span className="text-tx3">{c.at.slice(0, 10)}</span>
                {canUndo(c) ? (
                  <button
                    type="button"
                    onClick={() => void undo(c.id)}
                    disabled={busy === c.id}
                    className="glass-pill ml-auto rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-tx hover:border-ac hover:text-ac disabled:opacity-60"
                  >
                    {busy === c.id ? 'Undoing…' : 'Undo'}
                  </button>
                ) : null}
              </div>
              <p className="mt-1 text-tx2">{c.after}</p>
              <p className="mt-1 text-xs text-tx3">Before: {c.before || 'nothing (it was empty)'}</p>
              {c.error ? <p className="mt-1 text-xs text-red">{c.error}</p> : null}
            </li>
          ))}
        </ul>
      )}
      {note ? <p className={`mt-3 text-sm ${note.ok ? 'text-ac' : 'text-red'}`}>{note.text}</p> : null}
    </section>
  )
}

export function SeoPage() {
  const { brandId, brandLabel } = useBrand()
  const [data, setData] = useState<SeoInsights | null>(null)
  const [queue, setQueue] = useState<SeoFixQueue | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshNote, setRefreshNote] = useState<{ ok: boolean; text: string } | null>(null)
  const isSwingShack = brandId === 'swing-shack'

  const load = useCallback(() => {
    return getJson<{ ok: boolean; insights?: SeoInsights; error?: string }>('/api/seo/insights')
      .then((r) => {
        if (r.ok && r.insights) {
          setData(r.insights)
          setError(null)
        } else {
          setError(r.error || 'SEO insights unavailable')
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'SEO insights unavailable'))
  }, [])

  useEffect(() => {
    if (isSwingShack) void load()
  }, [isSwingShack, load])

  // The fix list is separate from the rankings: if it fails to load the rest of the page still works.
  useEffect(() => {
    if (!isSwingShack) return
    getJson<{ ok: boolean; queue?: SeoFixQueue | null }>('/api/seo/fix-queue?brand=swing-shack')
      .then((r) => setQueue(r.ok ? (r.queue ?? null) : null))
      .catch(() => setQueue(null))
  }, [isSwingShack])

  // Pulls fresh Ubersuggest data via POST /api/seo/refresh. The server needs
  // Ubersuggest tokens; the first-time login runs on the operator's Mac
  // (scripts/ubersuggest_oauth.py), so a missing-credentials reply tells them so.
  async function refresh() {
    setRefreshing(true)
    setRefreshNote(null)
    try {
      // Read the body on errors too: postJson drops it, and the 503 body carries the hint.
      const res = await fetch('/api/seo/refresh', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand: 'swing-shack' }),
      })
      const r = (await res.json().catch(() => ({ ok: false }))) as { ok: boolean; error?: string; hint?: string }
      if (r.ok) {
        setRefreshNote({ ok: true, text: 'Refreshed. Showing the new numbers.' })
        await load()
      } else {
        setRefreshNote({ ok: false, text: [r.error, r.hint].filter(Boolean).join(' — ') || 'Refresh failed' })
      }
    } catch (e: unknown) {
      setRefreshNote({ ok: false, text: e instanceof Error ? e.message : 'Refresh failed' })
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro icon={Search} badge="Results" here="/results/seo" title="SEO">
        Rankings and gaps for the Swing Shack website.
      </PageIntro>

      {!isSwingShack ? (
        <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
          <p className="text-sm text-tx2">
            SEO data is only tracked for Swing Shack right now{brandLabel ? `, not ${brandLabel}` : ''}. Switch the brand to Swing Shack to see it.
          </p>
        </section>
      ) : error ? (
        <section className="glass rounded-2xl border-[1.5px] border-red/40 p-5 backdrop-blur-xl">
          <p className="text-sm text-tx2">Could not load SEO data: {error}</p>
        </section>
      ) : !data ? (
        <p className="text-sm text-tx3">Loading SEO data…</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <StatCard icon={Activity} label="Domain authority" value={data.domain_health.domain_authority} hint={data.domain} tone="mute" />
            <StatCard
              icon={Activity}
              label="Top 3"
              value={data.domain_health.keyword_footprint.top_3}
              hint={`${data.domain_health.keyword_footprint.top_10} in top 10`}
              tone="green"
            />
            <StatCard
              icon={Activity}
              label="Ranking"
              value={data.domain_health.keyword_footprint.ranking_top_100}
              hint={`${data.domain_health.keyword_footprint.not_ranking} not ranking`}
              tone="mute"
            />
            <StatCard
              icon={Activity}
              label="Backlinks"
              value={data.domain_health.total_backlinks}
              hint={`${data.domain_health.ref_domains} referring domains`}
              tone="mute"
            />
          </div>

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <p className="text-sm text-tx2">{data.domain_health.manager_read}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              {Object.entries(data.freshness).map(([file, f]) => (
                <Badge key={file} tone={f.exists && f.fresh ? 'green' : 'red'}>
                  {file.replace('.json', '')}: {f.exists ? `${f.age_days ?? '?'} days old` : 'missing'}
                </Badge>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={refreshing}
                title="Pull fresh Ubersuggest rankings for swingshack.co.za"
                className="glass-pill inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-tx hover:border-ac hover:text-ac disabled:opacity-60"
              >
                <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} strokeWidth={2.5} />
                {refreshing ? 'Refreshing…' : `Refresh data${oldestAge(data) ? ` (${oldestAge(data)} days old)` : ''}`}
              </button>
              {refreshNote ? (
                <p className={`text-sm ${refreshNote.ok ? 'text-ac' : 'text-red'}`}>{refreshNote.text}</p>
              ) : null}
            </div>
            <p className="mt-2 text-xs text-tx3">
              Ubersuggest volumes are worldwide, not South African, and difficulty reads 0 in the cache.
            </p>
          </section>

          <FixesWaiting queue={queue} />

          <AutoChanges />

          <KeywordTable title="Winning" read="Top 10 or moved up this period." rows={data.winning} />
          <KeywordTable title="Quick wins" read="Close to page one; a small push may move them." rows={data.quick_wins} />
          <KeywordTable title="Leaking" read="Slipped down this period." rows={data.leaking} />
          <KeywordTable title="Missing" read="Tracked keywords we do not rank for yet." rows={data.missing} />

          <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h2 className="font-display text-lg font-semibold">Competitors</h2>
            {data.competitors.length === 0 ? (
              <p className="mt-2 text-sm text-tx3">No competitor data yet.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {data.competitors.map((c) => (
                  <li key={c.domain ?? ''} className="flex justify-between gap-3 border-t border-white/5 py-1.5">
                    <span className="text-tx">{c.domain}</span>
                    <span className="text-tx3">
                      DA {c.domain_authority ?? '—'} · {c.common_keywords ?? '—'} shared keywords
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {data.metadata.fetched_at ? (
            <p className="text-xs text-tx3">Rankings fetched {data.metadata.fetched_at}.</p>
          ) : null}
        </>
      )}
    </div>
  )
}
