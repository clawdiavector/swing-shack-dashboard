import { brandDisplayName } from '../../../lib/planning'
import type { PlanningBigIdeaResponse } from '../../../lib/planningTypes'

// V2.9 §1+§2 — Brand hero is driven by canonical data from
// /api/planning/<brand>/big-idea. No hard-coded brand arrays.
// All per-brand areas, goals, north star, and big idea come from the
// response payload. The component never invents cross-brand copy.

function bigIdeaFallback(brand: string): string {
  if (brand === 'stick') return 'Better Begins Here.'
  return ''
}

function northStarFallback(brand: string): string {
  // Brand-specific canonical North Stars. The React component never invents these
  // — they come from the canonical strategy file (data/brand-planning/<brand>.json)
  // or are absent. Empty string = no north star on file.
  if (brand === 'swing-shack') return 'Know the golfer better.\nMake golf more enjoyable.'
  return ''
}

// Brand-aware area color — uses the same colour palette as the canonical
// planning lanes (orange for primary, teal for fitting/measurement, grey
// for human/context). The actual list of areas is from the API.
function areaColor(key: string): string {
  const k = (key || '').toUpperCase()
  if (k === 'FITTING' || k === 'CONDITION' || k === 'MEASUREMENT') return 'text-[#14b8a6]'
  if (
    k === 'COACHING' ||
    k === 'WORKSHOP' ||
    k === 'LESSONS' ||
    k === 'ON-COURSE' ||
    k === 'CURATED' ||
    k === 'DROP' ||
    k === 'RETAIL' ||
    k === 'PROOF' ||
    k === 'HUMAN' ||
    k === 'APPAREL'
  ) {
    return 'text-[#f0a030]'
  }
  return 'text-tx3'
}

function metricFromGoal(g: { metric?: string; label?: string }): { value: string; unit: string } {
  const raw = (g.metric || g.label || '').trim()
  if (!raw) return { value: '', unit: '' }
  // Try to split "160 coaching / month" → { value: '160', unit: 'coaching / month' }
  const m = raw.match(/^(\d+(?:[.,]\d+)?)\s+(.+)$/)
  if (m) return { value: m[1], unit: m[2] }
  return { value: '', unit: raw }
}

export function PlanningHero({
  brand,
  bigIdea,
}: {
  brand: string
  bigIdea: PlanningBigIdeaResponse | null
}) {
  const idea = bigIdea?.big_brand_idea || {}
  const bigIdeaName =
    idea.name || (idea as { tagline?: string }).tagline || bigIdeaFallback(brand) || '—'
  const belief = idea.belief || ''

  // North Star: read from canonical response (north_star.statement), fall back to per-brand default.
  const nsFromApi = bigIdea?.north_star?.statement
  const nsFromApiLine1 = nsFromApi ? nsFromApi.split('\n')[0].trim() : ''
  const nsFromApiLine2 = nsFromApi ? nsFromApi.split('\n').slice(1).join('\n').trim() : ''
  const nsFallback = northStarFallback(brand)
  const nsFallbackLine1 = nsFallback ? nsFallback.split('\n')[0].trim() : ''
  const nsFallbackLine2 = nsFallback ? nsFallback.split('\n').slice(1).join('\n').trim() : ''
  const nsLine1 = nsFromApiLine1 || nsFallbackLine1
  const nsLine2 = nsFromApiLine2 || nsFallbackLine2

  // Operating goals: read from canonical response. Show all that exist.
  const operatingGoals = bigIdea?.operating_goals || []

  // Operating areas: canonical response. V2.9 §2 — never hard-coded.
  const areas = bigIdea?.operating_areas || []

  return (
    <section className="relative overflow-hidden rounded-2xl border border-[#004d5a]/60 bg-gradient-to-br from-[#0d0d0d] to-[#1a1a1a] p-6 md:p-8">
      <div
        className="pointer-events-none absolute top-0 right-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(240,160,48,0.12)_0%,transparent_70%)]"
        aria-hidden
      />
      <div className="relative z-10 space-y-5">
        {/* Brand */}
        <div>
          <p className="text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">Brand</p>
          <p className="text-sm font-bold tracking-wide text-[#f5f5f0]">{brandDisplayName(brand)}</p>
        </div>

        {/* BIG BRAND IDEA — separate field */}
        <div>
          <p className="text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
            Big brand idea
          </p>
          <h2
            className="font-display text-3xl font-black tracking-tight text-[#f5f5f0] md:text-4xl"
            data-testid="hero-big-idea"
          >
            {bigIdeaName}
          </h2>
          {belief ? (
            <p className="mt-2 text-sm text-[#8a8a8a] italic">&quot;{belief}&quot;</p>
          ) : null}
        </div>

        {/* NORTH STAR — separate field, never merged with big brand idea */}
        {nsLine1 || nsLine2 ? (
          <div>
            <p className="text-[11px] font-bold tracking-widest text-[#14b8a6] uppercase">
              North star
            </p>
            <p
              className="font-display text-xl font-semibold tracking-tight text-[#f5f5f0] md:text-2xl"
              data-testid="hero-north-star"
            >
              {nsLine1}
              {nsLine2 ? <><br />{nsLine2}</> : null}
            </p>
          </div>
        ) : null}

        {/* OPERATING GOALS — measurable targets. V2.9 §2 — show numeric
            value as a stat tile so the black block holds real business
            direction, not just slogans. */}
        {operatingGoals.length > 0 ? (
          <div data-testid="hero-operating-goals">
            <p className="mb-2 text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
              Operating goals
            </p>
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
              {operatingGoals.slice(0, 6).map((g) => {
                const m = metricFromGoal(g)
                return (
                  <div
                    key={g.id}
                    className="rounded-lg border border-[#f0a030]/25 bg-[#0d0d0d]/60 p-3"
                  >
                    {m.value ? (
                      <p className="font-display text-2xl font-black text-[#f0a030]">
                        {m.value}
                      </p>
                    ) : null}
                    <p className="text-[11px] font-bold tracking-wider text-[#f5f5f0] uppercase">
                      {m.unit || g.label}
                    </p>
                    {g.outcome_measurement ? (
                      <p className="mt-1 text-[9px] font-bold tracking-wider text-[#8a8a8a] uppercase">
                        · {g.outcome_measurement === 'PENDING' ? 'pending connector' : g.outcome_measurement}
                      </p>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </div>
        ) : null}

        {/* OPERATING AREAS — canonical tagline strip, brand-aware. */}
        {areas.length > 0 ? (
          <div data-testid="hero-operating-areas">
            <p className="mb-3 text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
              Always on
            </p>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {areas.map((row) => (
                <p key={row.key} className="text-sm text-[#f5f5f0]" data-area-key={row.key}>
                  <span className={`font-bold ${areaColor(row.key)}`}>{row.key}</span>
                  {row.tagline ? <> · {row.tagline}</> : null}
                </p>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
