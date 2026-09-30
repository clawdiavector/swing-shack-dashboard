import { useEffect, useMemo, useState } from 'react'
import { Calendar, ExternalLink, Loader2, MapPin, Search as SearchIcon } from 'lucide-react'
import { Tip } from '../../../components/ui'
import { brandDisplayName } from '../../../lib/planning'

// V2.9 §3+§4+§6+§7+§9 — Operator Date Intelligence.
//
// Search Dates panel. Pulls a unified result from
// GET /api/planning/<brand>/search?q=<query>. The backend searches
// across 5 layers in priority order:
//   1. Existing approved Calendar (spine + operator-approved records)
//   2. Existing Candidates / Watchlist (intelligence)
//   3. Existing Research Leads (intelligence without verified date)
//   4. Strategic Moments / important dates
//   5. Existing Scout intelligence
//
// Each result row shows: title, date, location, source, confidence,
// why-it-matters, suggested tier, recommended lead time, current state.
// Current state is one of: ON_MAIN_CALENDAR | CANDIDATE | WATCHLIST |
// RESEARCH_LEAD | STRATEGIC_MOMENT.
//
// Actions per state (V2.9 §7):
//   - verified candidate:        [+ ADD TO MAIN CALENDAR] [OPEN PLANNING]
//   - already approved:          [✓ ON MAIN CALENDAR]    [OPEN PLANNING]
//   - unverified research lead:  [VERIFY]                [OPEN INTELLIGENCE]
//   - strategic moment:          [OPEN PLANNING] (no Add — not promotable)
//
// V2.9 §9 — ADD TO MY CALENDAR uses the Google Calendar template URL
// (the existing public calendar connector) so we don't create parallel
// plumbing. The link is generated client-side and never mutates the
// Campaign OS approval state.

type SearchResultState = 'ON_MAIN_CALENDAR' | 'CANDIDATE' | 'WATCHLIST' | 'RESEARCH_LEAD' | 'STRATEGIC_MOMENT'

type SearchResult = {
  state: SearchResultState
  title: string
  date?: string
  end_date?: string
  location?: string
  source?: string
  source_url?: string
  confidence?: string
  why_it_matters?: string
  suggested_tier?: string
  recommended_lead_time_weeks?: number
  brand_id?: string
  candidate_id?: string
  event_key?: string
  category?: string
  origin?: string
  // V2.9 §6 — operator-supplied evidence marker
  evidence_kind?: 'OPERATOR_PROVIDED' | 'EXTERNAL_VERIFIED' | 'SCOUT' | 'DETERMINISTIC'
  // V2.9 §5 — only if user submitted via Suggest Date
  is_suggested?: boolean
}

type SearchResponse = {
  ok: boolean
  query: string
  brand_id: string
  counts: Record<SearchResultState, number>
  results: SearchResult[]
  search_more_available: boolean
  search_more_action?: string
}

const STATE_TONE: Record<SearchResultState, { bg: string; fg: string; label: string }> = {
  ON_MAIN_CALENDAR: { bg: 'bg-emerald-500/15', fg: 'text-emerald-400', label: '✓ ON MAIN CALENDAR' },
  CANDIDATE: { bg: 'bg-yel/15', fg: 'text-yel', label: 'CANDIDATE' },
  WATCHLIST: { bg: 'bg-purple-500/15', fg: 'text-purple-400', label: 'WATCHLIST' },
  RESEARCH_LEAD: { bg: 'bg-tx3/15', fg: 'text-tx3', label: 'RESEARCH LEAD' },
  STRATEGIC_MOMENT: { bg: 'bg-ac/15', fg: 'text-ac', label: 'STRATEGIC MOMENT' },
}

function buildPersonalCalendarUrl(args: {
  title: string
  date?: string
  end_date?: string
  details?: string
  location?: string
}): string {
  // V2.9 §9 — use Google Calendar's public render template (the
  // existing public calendar connector). The link is read-only and
  // NEVER mutates Campaign OS approval state.
  const base = 'https://calendar.google.com/calendar/render?action=TEMPLATE'
  const params = new URLSearchParams()
  params.set('text', args.title)
  if (args.date) {
    // Google expects YYYYMMDD for all-day events.
    if (args.end_date && args.end_date > args.date) {
      params.set('dates', `${args.date.replace(/-/g, '')}/${args.end_date.replace(/-/g, '')}`)
    } else {
      params.set('dates', `${args.date.replace(/-/g, '')}/${args.date.replace(/-/g, '')}`)
    }
  }
  if (args.location) params.set('location', args.location)
  if (args.details) {
    params.set('details', args.details)
  }
  return `${base}&${params.toString()}`
}

function ResultRow({
  r,
  brand,
  onAddToMain,
  onOpenPlanning,
  onVerify,
  onOpenIntelligence,
  adding,
}: {
  r: SearchResult
  brand: string
  onAddToMain: (r: SearchResult) => void
  onOpenPlanning: (r: SearchResult) => void
  onVerify: (r: SearchResult) => void
  onOpenIntelligence: (r: SearchResult) => void
  adding: boolean
}) {
  const tone = STATE_TONE[r.state] || STATE_TONE.RESEARCH_LEAD
  const personal = buildPersonalCalendarUrl({
    title: r.title,
    date: r.date,
    end_date: r.end_date,
    location: r.location,
    details: r.source_url
      ? `Campaign OS link: ${window.location.origin}/app/calendar/lanes?brand=${brand}\n\nSource: ${r.source_url}`
      : `Campaign OS link: ${window.location.origin}/app/calendar/lanes?brand=${brand}`,
  })

  return (
    <li
      className="rounded-lg border border-bd bg-bg2/60 p-3"
      data-testid="search-result-row"
      data-state={r.state}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-tx">{r.title}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-tx3">
            {r.date ? <span className="font-mono">{r.date}</span> : null}
            {r.end_date && r.end_date !== r.date ? <span>→ {r.end_date}</span> : null}
            {r.location ? (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3 w-3" /> {r.location}
              </span>
            ) : null}
            {r.suggested_tier ? <span className="text-yel">{r.suggested_tier}</span> : null}
            {r.recommended_lead_time_weeks != null ? (
              <span>lead {r.recommended_lead_time_weeks}w</span>
            ) : null}
            {r.confidence ? <span>conf: {r.confidence}</span> : null}
            {r.evidence_kind === 'OPERATOR_PROVIDED' ? (
              <span
                className="rounded bg-yel/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-yel uppercase"
                title="No external verification yet. May be later verified by Scout."
              >
                Operator provided
              </span>
            ) : null}
          </div>
          {r.why_it_matters ? (
            <p className="mt-1.5 text-[11px] text-tx2 italic">&quot;{r.why_it_matters}&quot;</p>
          ) : null}
          {r.source || r.source_url ? (
            <p className="mt-1 text-[10px] text-tx3">
              Source:{' '}
              {r.source_url ? (
                <a
                  href={r.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 text-yel hover:underline"
                >
                  {r.source || r.source_url}
                  <ExternalLink className="h-3 w-3" />
                </a>
              ) : (
                <span>{r.source}</span>
              )}
            </p>
          ) : null}
        </div>
        <span
          className={`rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wider uppercase ${tone.bg} ${tone.fg}`}
          data-testid="search-result-state"
        >
          {tone.label}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-bd pt-2">
        {r.state === 'ON_MAIN_CALENDAR' ? (
          <>
            <span
              data-testid="search-on-main"
              className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/15 px-2 py-1 text-[10px] font-bold tracking-wider text-emerald-400 uppercase"
            >
              ✓ ON MAIN CALENDAR
            </span>
            <button
              type="button"
              onClick={() => onOpenPlanning(r)}
              data-testid="search-open-planning"
              className="inline-flex items-center gap-1 rounded-md border border-bd bg-bg/60 px-2 py-1 text-[10px] font-bold tracking-wider text-tx2 uppercase hover:border-yel/60 hover:text-yel"
            >
              Open Planning
            </button>
          </>
        ) : r.state === 'CANDIDATE' || r.state === 'WATCHLIST' ? (
          <>
            <button
              type="button"
              onClick={() => onAddToMain(r)}
              disabled={adding || !r.candidate_id}
              data-testid="search-add-to-main"
              className="inline-flex items-center gap-1 rounded-md border border-yel/40 bg-yel/15 px-2 py-1 text-[10px] font-bold tracking-wider text-yel uppercase hover:bg-yel/25 disabled:opacity-50"
            >
              {adding ? <Loader2 className="h-3 w-3 animate-spin" /> : '+'}
              {adding ? 'Adding…' : 'Add to Main Calendar'}
            </button>
            <button
              type="button"
              onClick={() => onOpenPlanning(r)}
              data-testid="search-open-planning"
              className="inline-flex items-center gap-1 rounded-md border border-bd bg-bg/60 px-2 py-1 text-[10px] font-bold tracking-wider text-tx2 uppercase hover:border-yel/60 hover:text-yel"
            >
              Open Planning
            </button>
          </>
        ) : r.state === 'RESEARCH_LEAD' ? (
          <>
            <button
              type="button"
              onClick={() => onVerify(r)}
              data-testid="search-verify"
              className="inline-flex items-center gap-1 rounded-md border border-bd bg-bg/60 px-2 py-1 text-[10px] font-bold tracking-wider text-tx2 uppercase hover:border-yel/60 hover:text-yel"
            >
              Verify
            </button>
            <button
              type="button"
              onClick={() => onOpenIntelligence(r)}
              data-testid="search-open-intel"
              className="inline-flex items-center gap-1 rounded-md border border-bd bg-bg/60 px-2 py-1 text-[10px] font-bold tracking-wider text-tx2 uppercase hover:border-yel/60 hover:text-yel"
            >
              Open Intelligence
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onOpenPlanning(r)}
              data-testid="search-open-planning"
              className="inline-flex items-center gap-1 rounded-md border border-bd bg-bg/60 px-2 py-1 text-[10px] font-bold tracking-wider text-tx2 uppercase hover:border-yel/60 hover:text-yel"
            >
              Open Planning
            </button>
          </>
        )}

        <a
          href={personal}
          target="_blank"
          rel="noreferrer noopener"
          data-testid="add-to-my-calendar"
          data-action="personal-calendar"
          className="inline-flex items-center gap-1 rounded-md border border-ac/40 bg-ac/10 px-2 py-1 text-[10px] font-bold tracking-wider text-ac uppercase hover:bg-ac/20"
          title="Personal/work calendar reminder. Does NOT change Campaign OS approval."
        >
          <Calendar className="h-3 w-3" />
          Add to My Calendar
        </a>

        {r.is_suggested ? (
          <span
            className="rounded bg-tx3/15 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-tx3 uppercase"
            title="This is a Suggestion awaiting your decision. Not on the Main Calendar."
          >
            Suggested
          </span>
        ) : null}
      </div>
    </li>
  )
}

export function SearchPanel({
  brand,
  brandId,
  onAddToMainCalendar,
  onOpenPlanning,
  onOpenIntelligence,
  onOpenSuggestDateModal,
  refreshKey,
}: {
  brand: string
  brandId: string
  onAddToMainCalendar: (candidateId: string) => Promise<{ ok: boolean; error?: string }>
  onOpenPlanning: (candidateId: string) => void
  onOpenIntelligence: (candidateId: string) => void
  onOpenSuggestDateModal: () => void
  refreshKey?: number
}) {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [data, setData] = useState<SearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [addingId, setAddingId] = useState<string | null>(null)

  useEffect(() => {
    if (!submitted || !brandId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(
      `/api/planning/${encodeURIComponent(brandId)}/search?q=${encodeURIComponent(submitted)}`,
      { credentials: 'include' },
    )
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: SearchResponse) => {
        if (cancelled) return
        setData(j)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'search failed')
        setData(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [submitted, brandId, refreshKey])

  const counts = data?.counts || ({} as SearchResponse['counts'])
  const results = data?.results || []

  const exampleQueries = useMemo(
    () => [
      'Joburg Open 2027',
      'school holidays',
      'Black Friday',
      'golf events near Swing Shack',
    ],
    [],
  )

  return (
    <section
      data-testid="search-panel"
      className="glass space-y-3 rounded-2xl border border-white/10 p-4"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Search Dates</h2>
          <p className="mt-0.5 text-[11px] text-tx3">
            Find opportunities in {brandDisplayName(brand)}'s calendar, candidates, watchlist,
            research leads, and strategic moments.
          </p>
        </div>
        <Tip text="V2.9 §5 — your suggestion becomes a Candidate, not an approved event.">
          <button
            type="button"
            onClick={onOpenSuggestDateModal}
            data-testid="suggest-date-btn"
            className="inline-flex items-center gap-1 rounded-md border border-yel/40 bg-yel/15 px-3 py-1.5 text-[10px] font-bold tracking-wider text-yel uppercase hover:bg-yel/25"
          >
            + SUGGEST DATE
          </button>
        </Tip>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (query.trim()) setSubmitted(query.trim())
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <div className="flex min-w-[260px] flex-1 items-center gap-2 rounded-xl border border-white/10 bg-bg2/80 px-3 py-2">
          <SearchIcon className="h-4 w-4 text-tx3" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search events, dates or opportunities…"
            data-testid="search-input"
            className="w-full bg-transparent text-sm text-tx placeholder:text-tx3 focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={!query.trim() || loading}
          data-testid="search-submit"
          className="rounded-xl border border-yel/40 bg-yel/15 px-4 py-2 text-xs font-bold tracking-wider text-yel uppercase hover:bg-yel/25 disabled:opacity-50"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {!submitted ? (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-tx3">
          <span>Try:</span>
          {exampleQueries.map((eq) => (
            <button
              key={eq}
              type="button"
              onClick={() => {
                setQuery(eq)
                setSubmitted(eq)
              }}
              className="rounded-full border border-bd bg-bg2 px-2 py-0.5 hover:border-yel/60 hover:text-yel"
            >
              {eq}
            </button>
          ))}
        </div>
      ) : null}

      {error ? (
        <p className="text-sm text-red-400">Search failed: {error}</p>
      ) : null}

      {data && !error ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-tx3">
            <span className="font-bold tracking-wider uppercase">Search for &quot;{data.query}&quot;:</span>
            {Object.entries(counts).map(([k, v]) =>
              v > 0 ? (
                <span
                  key={k}
                  className={`rounded px-1.5 py-0.5 font-bold tracking-wider uppercase ${
                    STATE_TONE[k as SearchResultState]?.bg || 'bg-bd/40'
                  } ${STATE_TONE[k as SearchResultState]?.fg || 'text-tx3'}`}
                >
                  {STATE_TONE[k as SearchResultState]?.label || k} ({v})
                </span>
              ) : null,
            )}
            <span className="ml-1 text-tx3">· {results.length} result{results.length === 1 ? '' : 's'}</span>
          </div>

          {results.length === 0 ? (
            <div className="rounded-lg border border-bd bg-bg2/60 px-3 py-6 text-center text-sm text-tx3">
              <p>No matches yet.</p>
              {data.search_more_available ? (
                <p className="mt-1 text-[11px] text-tx2">
                  No adequate result exists — you can ask Scout to research more via the existing
                  research path.
                </p>
              ) : null}
            </div>
          ) : (
            <ul className="space-y-2" data-testid="search-results">
              {results.map((r, i) => (
                <ResultRow
                  key={`${r.state}-${r.title}-${i}`}
                  r={r}
                  brand={brandId}
                  onAddToMain={async (rr) => {
                    if (!rr.candidate_id) return
                    setAddingId(rr.candidate_id)
                    try {
                      await onAddToMainCalendar(rr.candidate_id)
                      // Re-run search so the row flips state.
                      setSubmitted(submitted)
                    } finally {
                      setAddingId(null)
                    }
                  }}
                  onOpenPlanning={(rr) => rr.candidate_id && onOpenPlanning(rr.candidate_id)}
                  onVerify={(rr) => rr.candidate_id && onOpenIntelligence(rr.candidate_id)}
                  onOpenIntelligence={(rr) => rr.candidate_id && onOpenIntelligence(rr.candidate_id)}
                  adding={addingId === r.candidate_id}
                />
              ))}
            </ul>
          )}

          {data.search_more_available ? (
            <div className="rounded-lg border border-dashed border-bd bg-bg2/40 p-3 text-center text-[11px] text-tx3">
              <p>
                Need more results? Ask Scout to research more via the existing research path.
              </p>
              <a
                href="/app/desk?tool=scout"
                className="mt-1 inline-block text-yel hover:underline"
                data-testid="search-research-more"
              >
                Research more →
              </a>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
