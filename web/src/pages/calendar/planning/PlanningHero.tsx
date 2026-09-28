import { brandDisplayName } from '../../../lib/planning'
import type { PlanningBigIdeaResponse } from '../../../lib/planningTypes'

// Swing Shack operating areas — sourced from canonical
// data/brand-planning/swing-shack.json#operating_areas. Rendered when brand=swing-shack.
// Each `key` is the always-on header; `tagline` is the one-line human description.
// These map 1:1 to lane IDs in the same file so the React component does not invent
// a parallel taxonomy.
const SWING_SHACK_AREAS = [
  { key: 'FITTING', color: 'text-[#f0a030]', tagline: 'fit first, buy second' },
  { key: 'COACHING', color: 'text-[#14b8a6]', tagline: 'TrackMan-backed sessions, real numbers' },
  { key: 'LESSONS', color: 'text-[#f0a030]', tagline: 'the actual lesson moments' },
  { key: 'ON-COURSE', color: 'text-[#f0a030]', tagline: 'where the data meets the grass' },
  { key: 'HUMAN', color: 'text-tx3', tagline: 'the real coaches, the real golfers' },
  { key: 'MEASUREMENT', color: 'text-tx3', tagline: 'TrackMan data, what the numbers mean' },
]

// Stick standard — pre-existing always-on headers for brand=stick.
// DO NOT add "ask Stick" / "built at Stick" cross-brand copy.
const STICK_AREAS = [
  { key: 'RETAIL', color: 'text-[#f0a030]', tagline: 'real stock only — earns its place' },
  { key: 'FITTING', color: 'text-[#14b8a6]', tagline: 'fit first, buy second' },
  { key: 'COACHING', color: 'text-[#f0a030]', tagline: 'coaching that proves itself' },
  { key: 'WORKSHOP', color: 'text-tx3', tagline: 'built in our workshop' },
  { key: 'HUMAN', color: 'text-tx3', tagline: 'the real people behind it' },
  { key: 'APPAREL', color: 'text-tx3', tagline: 'style that belongs' },
]

// Bag Drop — e-commerce store, different again.
const BAG_DROP_AREAS = [
  { key: 'CURATED', color: 'text-[#f0a030]', tagline: 'quality used clubs, demo models, essentials' },
  { key: 'CONDITION', color: 'text-[#14b8a6]', tagline: 'honest A/B/C grade on every club' },
  { key: 'DROP', color: 'text-[#f0a030]', tagline: 'weekly stock release' },
  { key: 'PROOF', color: 'text-tx3', tagline: 'OUT THE DOOR — packed, shipped, gone' },
]

function areasFor(brand: string): { key: string; color: string; tagline: string }[] {
  if (brand === 'swing-shack') return SWING_SHACK_AREAS
  if (brand === 'stick') return STICK_AREAS
  if (brand === 'bag-drop') return BAG_DROP_AREAS
  return []
}

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

  // Operating areas: rendered tagline strip. Brand-aware.
  const areas = areasFor(brand)

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

        {/* OPERATING GOALS — separate, measurable targets */}
        {operatingGoals.length > 0 ? (
          <div data-testid="hero-operating-goals">
            <p className="mb-2 text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
              Operating goals
            </p>
            <ul className="space-y-1.5">
              {operatingGoals.map((g) => (
                <li key={g.id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-bold text-[#f5f5f0]">{g.label}</span>
                  <span className="text-[#f5f5f0]">{g.metric}</span>
                  <span className="text-[10px] font-bold tracking-wider text-[#8a8a8a] uppercase">
                    · {g.outcome_measurement === 'PENDING' ? 'pending connector' : g.outcome_measurement}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* OPERATING AREAS — always-on tagline strip. Brand-specific, no cross-brand copy. */}
        {areas.length > 0 ? (
          <div data-testid="hero-operating-areas">
            <p className="mb-3 text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
              Always on · {brandDisplayName(brand)} standard
            </p>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {areas.map((row) => (
                <p key={row.key} className="text-sm text-[#f5f5f0]">
                  <span className={`font-bold ${row.color}`}>{row.key}</span> · {row.tagline}
                </p>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
