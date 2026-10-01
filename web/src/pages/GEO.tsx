import { BarChart3, BookOpen, BotMessageSquare, CheckCircle, ClipboardList, Eye, RefreshCw, Search, Star, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { Badge } from '../components/ui'
import { getJson, postJson } from '../lib/api'

// ── Types ──────────────────────────────────────────────────────────────────────

interface CitationEntry {
  id: string
  model: string
  prompt: string
  answer_text: string
  mentions_brand: boolean
  mentions_url: boolean
  url_cited: string | null
  date: string
  added_at: string
}

interface Scorecard {
  total_queries: number
  citation_rate: number | null
  url_citation_rate: number | null
  weekly_delta: number | null
  top_models: { model: string; count: number }[]
  recent: CitationEntry[]
}

interface WatchlistEntry {
  query: string
  region?: string
  added_at: string
}

interface GeoCheck {
  check: string
  signal_type?: 'AI_CITATION' | 'ENTITY_DISCOVERY' | 'TECHNICAL_SEO' | 'SOCIAL_METADATA' | 'EXPERIMENTAL'
  status: string
  severity: string
  message: string
  fix_suggestion: string | null
  excluded_from_score?: boolean
}

interface AuditResult {
  ok: boolean
  brand: string
  domain: string
  fetched_at: string
  checks: GeoCheck[]
  seo_findings: GeoCheck[]
  wp_posts_checked: number
  wp_reachable: boolean
}

interface ApplyFixResult {
  status: string
  check: string
  details: Record<string, unknown>
  audit_trail: Record<string, unknown>
}

// V1.1 (2026-10-01): GEO score is split into OBSERVED AI PERFORMANCE
// (the primary score, from real citation records) and SITE READINESS
// (supporting diagnostic). One must not masquerade as the other.
interface ObservedAI {
  citation_rate: number | null
  url_citation_rate: number | null
  query_coverage: number | null
  competitor_share: number | null
  weekly_delta: number | null
  top_models: { model: string; count: number }[]
  recent: Array<Record<string, unknown>>
}

interface SiteReadinessCheck {
  check: string
  signal_type?: string
  status: string
  severity: string
  excluded_from_score?: boolean
}

interface SiteReadiness {
  ok: boolean
  checks: SiteReadinessCheck[]
  domain?: string
  fetched_at?: string
  error?: string | null
}

interface Scorecard {
  ok: boolean
  brand: string
  stage: 'NO_DATA' | 'BASELINE' | 'TRENDING'
  n: number
  sample_size_label: string
  observed_ai_performance: ObservedAI
  site_readiness: SiteReadiness
  disclaimer: string
  generated_at: string
}

// ── Sub-components ──────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, { label: string; tone: string }> = {
    high: { label: 'HIGH', tone: 'red' },
    medium: { label: 'MED', tone: 'yellow' },
    low: { label: 'LOW', tone: 'green' },
  }
  const { label, tone } = map[severity] ?? { label: severity.toUpperCase(), tone: 'mute' }
  return <Badge tone={tone as 'red' | 'gold' | 'green' | 'mute'}>{label}</Badge>
}

function StatusDot({ status }: { status: string }) {
  if (status === 'OK') return <CheckCircle className="h-4 w-4 text-ac" />
  if (status === 'CHECK_FAILED') return <span className="h-2.5 w-2.5 rounded-full bg-tx3 inline-block" />
  return <span className="h-2.5 w-2.5 rounded-full bg-yel inline-block" />
}

function KpiTile({ label, value, sub, tone = 'default' }: {
  label: string; value: string | number | null; sub?: string; tone?: 'good' | 'bad' | 'neutral' | 'default'
}) {
  const valColor = tone === 'good' ? 'text-ac' : tone === 'bad' ? 'text-rd' : 'text-tx'
  return (
    <div className="glass rounded-2xl border-[1.5px] border-white/10 px-4 py-3 backdrop-blur-xl">
      <p className="text-[11px] font-semibold tracking-widest text-tx3 uppercase">{label}</p>
      <p className={`mt-1 font-display text-3xl font-semibold ${valColor}`}>
        {value ?? '—'}
      </p>
      {sub && <p className="mt-0.5 text-xs text-tx3">{sub}</p>}
    </div>
  )
}

function CopyBlock({ content, label }: { content: string; label: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <div className="relative mt-2 rounded-xl border border-white/10 bg-black/40">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/5">
        <span className="text-[11px] font-semibold text-tx3">{label}</span>
        <button
          onClick={copy}
          className="flex items-center gap-1 text-[11px] text-yel hover:text-yel/80 transition-colors"
        >
          {copied ? <CheckCircle className="h-3 w-3" /> : null}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs text-tx2 whitespace-pre-wrap break-all max-h-64">{content}</pre>
    </div>
  )
}

// ── Tabs ───────────────────────────────────────────────────────────────────────

type TabId = 'scorecard' | 'watchlist' | 'citations' | 'audit'

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'scorecard', label: 'Scorecard', icon: BarChart3 },
  { id: 'watchlist', label: 'Watchlist', icon: Search },
  { id: 'citations', label: 'Citations', icon: BotMessageSquare },
  { id: 'audit', label: 'Audit & Fixes', icon: ClipboardList },
]

// ── Model options ─────────────────────────────────────────────────────────────

const MODELS = [
  { value: 'chatgpt', label: 'ChatGPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'perplexity', label: 'Perplexity' },
  { value: 'google-ai-overview', label: 'Google AI Overview' },
  { value: 'gemini', label: 'Gemini' },
]

// ── Main component ────────────────────────────────────────────────────────────

export default function GEO() {
  const { brandId } = useBrand()
  const [tab, setTab] = useState<TabId>('scorecard')
  const [scorecard, setScorecard] = useState<Scorecard | null>(null)
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([])
  const [citations, setCitations] = useState<CitationEntry[]>([])
  const [audit, setAudit] = useState<AuditResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Citation form state
  const [model, setModel] = useState('chatgpt')
  const [prompt, setPrompt] = useState('')
  const [answerText, setAnswerText] = useState('')
  const [mentionsBrand, setMentionsBrand] = useState(false)
  const [mentionsUrl, setMentionsUrl] = useState(false)
  const [urlCited, setUrlCited] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Watchlist form
  const [newQuery, setNewQuery] = useState('')
  const [submittingWl, setSubmittingWl] = useState(false)

  // Apply fix state
  const [fixResults, setFixResults] = useState<Record<string, ApplyFixResult>>({})

  const brand = brandId || 'swing-shack'

  const loadAll = useCallback(async () => {
    if (!brand) return
    setLoading(true)
    setError(null)
    try {
      const [sc, wl, cit, aud] = await Promise.all([
        getJson<{ ok: boolean } & Scorecard>(`/api/geo/scorecard?brand=${encodeURIComponent(brand)}`),
        getJson<{ ok: boolean; watchlist: WatchlistEntry[] }>(`/api/geo/watchlist?brand=${encodeURIComponent(brand)}`),
        getJson<{ ok: boolean; citations: CitationEntry[] }>(`/api/geo/citations?brand=${encodeURIComponent(brand)}`),
        getJson<AuditResult>(`/api/geo/audit?brand=${encodeURIComponent(brand)}`),
      ])
      if (sc.ok) setScorecard(sc)
      if (wl.ok) setWatchlist(wl.watchlist)
      if (cit.ok) setCitations(cit.citations)
      if (aud?.ok) setAudit(aud)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [brand])

  useEffect(() => { void loadAll() }, [loadAll])

  const handleAddCitation = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim() && !answerText.trim()) return
    setSubmitting(true)
    try {
      const res = await postJson<{ ok: boolean; entry: CitationEntry }>('/api/geo/citations', {
        brand,
        model,
        prompt,
        answer_text: answerText,
        mentions_brand: mentionsBrand,
        mentions_url: mentionsUrl,
        url_cited: urlCited || undefined,
        date: new Date().toISOString().slice(0, 10),
      })
      if (res.ok) {
        setCitations(prev => [...prev, res.entry])
        setPrompt('')
        setAnswerText('')
        setMentionsBrand(false)
        setMentionsUrl(false)
        setUrlCited('')
        void loadAll()
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteCitation = async (idx: number) => {
    await fetch(`/api/geo/citations/${idx}?brand=${encodeURIComponent(brand)}`, { method: 'DELETE', credentials: 'same-origin' })
    setCitations(prev => prev.filter((_, i) => i !== idx))
    void loadAll()
  }

  const handleAddWatchlist = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newQuery.trim()) return
    setSubmittingWl(true)
    try {
      const res = await postJson<{ ok: boolean; entry: WatchlistEntry }>('/api/geo/watchlist', {
        brand,
        query: newQuery.trim(),
      })
      if (res.ok) {
        setWatchlist(prev => [...prev, res.entry])
        setNewQuery('')
      }
    } finally {
      setSubmittingWl(false)
    }
  }

  const handleDeleteWatchlist = async (query: string) => {
    await postJson('/api/geo/watchlist', { brand, query })
    setWatchlist(prev => prev.filter(w => w.query !== query))
  }

  const handleApplyFix = async (check: string, fixId: string) => {
    const res = await postJson<ApplyFixResult>('/api/geo/apply-fix', { brand, check, fix_id: fixId })
    setFixResults(prev => ({ ...prev, [`${check}:${fixId}`]: res }))
  }

  const allChecks = [
    ...(audit?.checks ?? []),
    ...(audit?.seo_findings ?? []),
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <BotMessageSquare className="h-5 w-5 text-yel" />
            <span className="text-xs font-semibold tracking-widest text-yel uppercase">Insights</span>
          </div>
          <h1 className="font-display text-3xl font-semibold text-tx">GEO & AI Citation Health</h1>
          <p className="mt-1 text-sm text-tx3">
            Generative Engine Optimisation — get cited by ChatGPT, Claude, Perplexity, Google AI Overviews.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadAll()}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-60"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/10">
        {TABS.map(t => {
          const Icon = t.icon
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold transition-colors border-b-2 -mb-px ${
                tab === t.id
                  ? 'border-yel text-yel'
                  : 'border-transparent text-tx3 hover:text-tx hover:border-white/20'
              }`}
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {loading && !scorecard && (
        <div className="flex items-center justify-center py-16">
          <RefreshCw className="h-6 w-6 text-yel animate-spin" />
          <span className="ml-3 text-tx3">Loading GEO data…</span>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rd/40 bg-rd/10 px-4 py-3 text-sm text-rd">
          {error}
        </div>
      )}

      {/* ── SCORECARD TAB ── */}
      {tab === 'scorecard' && scorecard && (
        <div className="space-y-5">
          {/* V1.1: stage + sample-size label must always be visible above the
              numbers so operators never see a meaningful-looking citation
              percentage when the sample is tiny. */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${
                  scorecard.stage === 'NO_DATA'
                    ? 'bg-tx3/15 text-tx3'
                    : scorecard.stage === 'BASELINE'
                    ? 'bg-yel/15 text-yel'
                    : 'bg-ac/15 text-ac'
                }`}
              >
                {scorecard.stage}
              </span>
              <span className="text-sm text-tx2">{scorecard.sample_size_label}</span>
            </div>
            <span className="text-[11px] text-tx3 italic max-w-xl text-right">
              {scorecard.disclaimer}
            </span>
          </div>

          {/* OBSERVED AI PERFORMANCE — the primary GEO score. Always shown.
              Empty values stay blank — never a fake 0%. */}
          <section>
            <div className="mb-2 flex items-center gap-2">
              <h3 className="font-display text-sm font-semibold uppercase tracking-wide text-tx2">
                Observed AI performance
              </h3>
              <span className="text-[10px] text-tx3">primary GEO score</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <KpiTile
                label="n observations"
                value={scorecard.n}
                sub={scorecard.stage === 'NO_DATA' ? 'paste LLM answers to populate' : 'past 30 days'}
              />
              <KpiTile
                label="Brand citation rate"
                value={
                  scorecard.observed_ai_performance.citation_rate != null
                    ? `${scorecard.observed_ai_performance.citation_rate}%`
                    : null
                }
                sub={
                  scorecard.stage === 'NO_DATA'
                    ? 'n too small to report'
                    : 'mentions brand name'
                }
              />
              <KpiTile
                label="URL citation rate"
                value={
                  scorecard.observed_ai_performance.url_citation_rate != null
                    ? `${scorecard.observed_ai_performance.url_citation_rate}%`
                    : null
                }
                sub={
                  scorecard.stage === 'NO_DATA'
                    ? 'n too small to report'
                    : 'cites your domain'
                }
              />
              <KpiTile
                label="Query coverage"
                value={scorecard.observed_ai_performance.query_coverage}
                sub="distinct watchlist queries with at least 1 observation"
              />
              <KpiTile
                label="Competitor share"
                value={
                  scorecard.observed_ai_performance.competitor_share != null
                    ? `${scorecard.observed_ai_performance.competitor_share}%`
                    : null
                }
                sub="answers mentioning a competitor"
              />
              <KpiTile
                label="Weekly delta"
                value={
                  scorecard.observed_ai_performance.weekly_delta != null
                    ? `${scorecard.observed_ai_performance.weekly_delta > 0 ? '+' : ''}${scorecard.observed_ai_performance.weekly_delta}%`
                    : null
                }
                sub="vs prior 7d window"
              />
            </div>
          </section>

          {/* SITE READINESS — supporting diagnostic. Never blended into the
              primary score. Shown as a separate bucket with a clear label
              so operators know these are NOT citations. */}
          <section>
            <div className="mb-2 flex items-center gap-2">
              <h3 className="font-display text-sm font-semibold uppercase tracking-wide text-tx2">
                Site readiness
              </h3>
              <span className="text-[10px] text-tx3">supporting diagnostic · not citation rate</span>
            </div>
            {!scorecard.site_readiness.ok ? (
              <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-tx3">
                {scorecard.site_readiness.error
                  ? `Audit fetch failed: ${scorecard.site_readiness.error}`
                  : 'Audit fetch in progress…'}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {scorecard.site_readiness.checks.map((c, i) => (
                  <div
                    key={i}
                    className={`rounded-xl border bg-white/5 p-3 ${
                      c.excluded_from_score ? 'border-dashed border-white/10' : 'border-white/10'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-mono uppercase tracking-wide text-tx3">
                        {c.signal_type || 'TECHNICAL_SEO'}
                      </span>
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          c.status === 'OK'
                            ? 'bg-ac/15 text-ac'
                            : c.status === 'UNKNOWN' || c.excluded_from_score
                            ? 'bg-tx3/15 text-tx3'
                            : 'bg-yel/15 text-yel'
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>
                    <div className="mt-1 text-sm font-semibold text-tx">{c.check.replace(/_/g, ' ')}</div>
                    {c.excluded_from_score && (
                      <div className="mt-1 text-[10px] italic text-tx3">excluded from score</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {scorecard.observed_ai_performance.top_models.length > 0 && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
              <h3 className="mb-3 font-display text-base font-semibold text-tx">Top models observed</h3>
              <div className="flex flex-wrap gap-2">
                {scorecard.observed_ai_performance.top_models.map(m => (
                  <span key={m.model} className="flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-sm text-tx2">
                    <Star className="h-3 w-3 text-yel" />
                    {m.model} · {m.count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {scorecard.observed_ai_performance.recent.length > 0 && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
              <h3 className="mb-3 font-display text-base font-semibold text-tx">Recent observations</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5 text-left text-xs font-semibold text-tx3 uppercase tracking-wider">
                    <th className="pb-2">Model</th>
                    <th className="pb-2">Date</th>
                    <th className="pb-2">Brand?</th>
                    <th className="pb-2">URL?</th>
                  </tr>
                </thead>
                <tbody>
                  {scorecard.observed_ai_performance.recent.map((c, i) => (
                    <tr key={(c.id as string) ?? i} className="border-b border-white/5 last:border-0">
                      <td className="py-2 text-tx2">{String(c.model ?? c.model_provider ?? '')}</td>
                      <td className="py-2 text-tx3">{String(c.date ?? '')}</td>
                      <td className="py-2">
                        {c.mentions_brand
                          ? <CheckCircle className="h-4 w-4 text-ac" />
                          : <X className="h-4 w-4 text-rd/60" />}
                      </td>
                      <td className="py-2">
                        {c.mentions_url
                          ? <CheckCircle className="h-4 w-4 text-ac" />
                          : <X className="h-4 w-4 text-rd/60" />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {scorecard.n === 0 && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-8 text-center backdrop-blur-xl">
              <BotMessageSquare className="mx-auto h-10 w-10 text-tx3 mb-3" />
              <p className="text-tx2 font-semibold">No observations yet</p>
              <p className="mt-1 text-sm text-tx3">Paste your first LLM answer in the Citations tab to start a baseline.</p>
            </div>
          )}
        </div>
      )}

      {/* ── WATCHLIST TAB ── */}
      {tab === 'watchlist' && (
        <div className="space-y-4">
          <div className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
            <h3 className="mb-3 font-display text-base font-semibold text-tx">Add canonical query</h3>
            <form onSubmit={e => void handleAddWatchlist(e)} className="flex gap-2">
              <input
                type="text"
                value={newQuery}
                onChange={e => setNewQuery(e.target.value)}
                placeholder="e.g. indoor golf Johannesburg"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-tx placeholder-tx3 focus:border-yel/50 focus:outline-none"
              />
              <button type="submit" disabled={submittingWl} className="inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-60">
                <BookOpen className="h-4 w-4" />
                {submittingWl ? 'Adding…' : 'Add'}
              </button>
            </form>
          </div>

          {watchlist.length === 0 ? (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-8 text-center backdrop-blur-xl">
              <Search className="mx-auto h-10 w-10 text-tx3 mb-3" />
              <p className="text-tx2 font-semibold">No watchlist queries</p>
              <p className="mt-1 text-sm text-tx3">Add queries you want to track for AI citation.</p>
            </div>
          ) : (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
              <h3 className="mb-3 font-display text-base font-semibold text-tx">
                Watchlist ({watchlist.length})
              </h3>
              <ul className="space-y-2">
                {watchlist.map((w, i) => (
                  <li key={i} className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Search className="h-4 w-4 text-yel shrink-0" />
                      <span className="text-sm text-tx2">{w.query}</span>
                      {w.region && (
                        <span className="text-[10px]"><Badge tone="mute">{w.region}</Badge></span>
                      )}
                    </div>
                    <button
                      onClick={() => void handleDeleteWatchlist(w.query)}
                      className="text-tx3 hover:text-rd transition-colors"
                      title="Remove"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── CITATIONS TAB ── */}
      {tab === 'citations' && (
        <div className="space-y-4">
          {/* Add form */}
          <form onSubmit={e => void handleAddCitation(e)} className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl space-y-4">
            <h3 className="font-display text-base font-semibold text-tx">Paste an LLM answer</h3>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold text-tx3 uppercase tracking-wider">Model</label>
                <select
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-tx focus:border-yel/50 focus:outline-none"
                >
                  {MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-tx3 uppercase tracking-wider">Date</label>
                <input
                  type="date"
                  defaultValue={new Date().toISOString().slice(0, 10)}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-tx focus:border-yel/50 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-tx3 uppercase tracking-wider">
                Prompt <span className="text-tx3 normal-case">(what you asked)</span>
              </label>
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={2}
                placeholder="e.g. What's the best indoor golf in Johannesburg?"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-tx placeholder-tx3 focus:border-yel/50 focus:outline-none resize-none"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-tx3 uppercase tracking-wider">
                LLM Answer <span className="text-tx3 normal-case">(paste the answer here)</span>
              </label>
              <textarea
                value={answerText}
                onChange={e => setAnswerText(e.target.value)}
                rows={6}
                placeholder="Paste the full LLM answer here…"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-tx placeholder-tx3 focus:border-yel/50 focus:outline-none resize-none"
              />
            </div>

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-tx2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={mentionsBrand}
                  onChange={e => setMentionsBrand(e.target.checked)}
                  className="accent-yel"
                />
                Mentions brand name
              </label>
              <label className="flex items-center gap-2 text-sm text-tx2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={mentionsUrl}
                  onChange={e => setMentionsUrl(e.target.checked)}
                  className="accent-yel"
                />
                Mentions URL
              </label>
            </div>

            {mentionsUrl && (
              <div>
                <label className="mb-1 block text-xs font-semibold text-tx3 uppercase tracking-wider">URL cited</label>
                <input
                  type="url"
                  value={urlCited}
                  onChange={e => setUrlCited(e.target.value)}
                  placeholder="https://swingshack.co.za/…"
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-tx placeholder-tx3 focus:border-yel/50 focus:outline-none"
                />
              </div>
            )}

            <button type="submit" disabled={submitting} className="inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-60">
              <BotMessageSquare className="h-4 w-4" />
              {submitting ? 'Adding…' : 'Add citation'}
            </button>
          </form>

          {/* Citation list */}
          {citations.length > 0 && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
              <h3 className="mb-3 font-display text-base font-semibold text-tx">
                Citation log ({citations.length})
              </h3>
              <ul className="space-y-3">
                {citations.slice().reverse().map((c, i) => (
                  <li key={c.id ?? i} className="rounded-xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px]"><Badge tone="gold">{c.model}</Badge></span>
                        <span className="text-xs text-tx3">{c.date}</span>
                      </div>
                      <button
                        onClick={() => void handleDeleteCitation(citations.length - 1 - i)}
                        className="text-tx3 hover:text-rd transition-colors shrink-0"
                        title="Delete"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    {c.prompt && (
                      <p className="mb-1.5 text-xs font-semibold text-tx3 uppercase tracking-wider">Prompt</p>
                    )}
                    {c.prompt && (
                      <p className="mb-2 text-sm text-tx2 italic border-l-2 border-yel/40 pl-3">{c.prompt}</p>
                    )}
                    {c.answer_text && (
                      <>
                        <p className="mb-1.5 text-xs font-semibold text-tx3 uppercase tracking-wider">Answer excerpt</p>
                        <p className="text-sm text-tx2 line-clamp-4">{c.answer_text.slice(0, 300)}{c.answer_text.length > 300 ? '…' : ''}</p>
                      </>
                    )}
                    <div className="mt-3 flex items-center gap-4 text-xs text-tx3">
                      {c.mentions_brand ? (
                        <span className="flex items-center gap-1 text-ac"><CheckCircle className="h-3 w-3" />Brand cited</span>
                      ) : (
                        <span className="flex items-center gap-1 text-rd/60"><X className="h-3 w-3" />No brand</span>
                      )}
                      {c.mentions_url ? (
                        <span className="flex items-center gap-1 text-ac"><CheckCircle className="h-3 w-3" />URL cited</span>
                      ) : (
                        <span className="flex items-center gap-1 text-rd/60"><X className="h-3 w-3" />No URL</span>
                      )}
                      {c.url_cited && <span className="text-yel">{c.url_cited}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {citations.length === 0 && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-8 text-center backdrop-blur-xl">
              <BotMessageSquare className="mx-auto h-10 w-10 text-tx3 mb-3" />
              <p className="text-tx2 font-semibold">No citations logged</p>
              <p className="mt-1 text-sm text-tx3">Use the form above to paste your first LLM answer.</p>
            </div>
          )}
        </div>
      )}

      {/* ── AUDIT TAB ── */}
      {tab === 'audit' && (
        <div className="space-y-4">
          {audit && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 px-4 py-2.5 backdrop-blur-xl flex items-center justify-between">
              <div className="text-xs text-tx3">
                {audit.wp_reachable ? (
                  <span className="flex items-center gap-1.5">
                    <CheckCircle className="h-3.5 w-3.5 text-ac" />WP reachable · checked {audit.wp_posts_checked} posts · fetched {new Date(audit.fetched_at).toLocaleString()}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-yel inline-block" />WP unreachable · using cached data
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={async () => {
                  const fresh = await getJson<AuditResult>(`/api/geo/audit?brand=${encodeURIComponent(brand)}&force_refresh=true`)
                  if (fresh?.ok) setAudit(fresh)
                }}
                className="inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-60"
              >
                <RefreshCw className="h-4 w-4" />
                Force refresh
              </button>
            </div>
          )}

          {allChecks.length === 0 && (
            <div className="glass rounded-2xl border-[1.5px] border-white/10 p-8 text-center backdrop-blur-xl">
              <ClipboardList className="mx-auto h-10 w-10 text-tx3 mb-3" />
              <p className="text-tx2 font-semibold">Audit not yet run</p>
              <p className="mt-1 text-sm text-tx3">Refresh the page to run the GEO audit checks.</p>
            </div>
          )}

          {allChecks.length > 0 && (
            <div className="space-y-2">
              {allChecks.map((check, i) => {
                const fixKey = `${check.check}:${check.fix_suggestion ? i : 'none'}`
                const fixResult = fixResults[fixKey]
                return (
                  <div key={i} className="glass rounded-2xl border-[1.5px] border-white/10 p-4 backdrop-blur-xl">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5">
                        <StatusDot status={check.status} />
                        <div>
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-sm font-semibold text-tx">{check.check.replace(/_/g, ' ')}</span>
                            <SeverityBadge severity={check.severity} />
                          </div>
                          <p className="text-sm text-tx2">{check.message}</p>
                        </div>
                      </div>
                      {check.fix_suggestion && (
                        <button
                          type="button"
                          onClick={() => void handleApplyFix(check.check, String(i))}
                          className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-60"
                        >
                          {check.status === 'OK' ? <CheckCircle className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          {check.status === 'OK' ? 'View fix' : 'Apply / view'}
                        </button>
                      )}
                    </div>

                    {fixResult && (
                      <div className="mt-3 rounded-xl border border-yel/30 bg-yel/5 p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge tone="gold">{fixResult.status}</Badge>
                          <span className="text-xs text-tx3">
                            {fixResult.status === 'APPLIED'
                              ? 'Fix applied successfully via WP REST.'
                              : fixResult.status === 'PARTIAL_APPLIED'
                              ? 'Partially applied — operator action needed.'
                              : 'Manual approval required — copy and paste the content below.'}
                          </span>
                        </div>
                        {fixResult.details && (
                          <>
                            {fixResult.details.note && (
                              <p className="mb-2 text-sm text-tx2">{fixResult.details.note as string}</p>
                            )}
                            {fixResult.details.instructions && (
                              <p className="mb-2 text-xs text-tx3 whitespace-pre-wrap">{fixResult.details.instructions as string}</p>
                            )}
                            {fixResult.details.paste_instruction && (
                              <p className="mb-2 text-xs text-tx3 whitespace-pre-wrap">{fixResult.details.paste_instruction as string}</p>
                            )}
                            {fixResult.details.jsonld && (
                              <CopyBlock content={fixResult.details.jsonld as string} label="JSON-LD to paste" />
                            )}
                            {fixResult.details.content && (
                              <CopyBlock content={fixResult.details.content as string} label="llms.txt content" />
                            )}
                            {fixResult.details.og_tags && (
                              <CopyBlock content={fixResult.details.og_tags as string} label="Open Graph tags" />
                            )}
                            {fixResult.details.twitter_tags && (
                              <CopyBlock content={fixResult.details.twitter_tags as string} label="Twitter Card tags" />
                            )}
                            {fixResult.details.jsonld === undefined && fixResult.details.content === undefined &&
                             fixResult.details.og_tags === undefined && fixResult.details.twitter_tags === undefined &&
                             fixResult.details.note === undefined && (
                              <CopyBlock content={JSON.stringify(fixResult.details, null, 2)} label="Details" />
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Navigation link */}
      <div className="pt-2 border-t border-white/5">
        <a href="/results" className="text-xs text-yel hover:text-yel/80 transition-colors flex items-center gap-1">
          ← Back to Results
        </a>
      </div>
    </div>
  )
}
