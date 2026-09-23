import { brandDisplayName } from '../../../lib/planning'
import type { PlanningBigIdeaResponse } from '../../../lib/planningTypes'

const STICK_STANDARD = [
  { key: 'RETAIL', color: 'text-[#f0a030]', text: 'real stock only — earns its place' },
  { key: 'FITTING', color: 'text-[#14b8a6]', text: 'fit first, buy second' },
  { key: 'COACHING', color: 'text-[#f0a030]', text: 'ask Stick' },
  { key: 'WORKSHOP', color: 'text-tx3', text: 'built at Stick' },
  { key: 'HUMAN', color: 'text-tx3', text: 'the real people' },
  { key: 'APPAREL', color: 'text-tx3', text: 'style that belongs' },
]

export function PlanningHero({
  brand,
  bigIdea,
}: {
  brand: string
  bigIdea: PlanningBigIdeaResponse | null
}) {
  const idea = bigIdea?.big_brand_idea || {}
  const bigIdeaName =
    idea.name || (brand === 'stick' ? 'Better Begins Here.' : '—')
  const belief =
    idea.belief || (brand === 'stick' ? 'Everything has to earn its place.' : '')

  return (
    <section className="relative overflow-hidden rounded-2xl border border-[#004d5a]/60 bg-gradient-to-br from-[#0d0d0d] to-[#1a1a1a] p-6 md:p-8">
      <div
        className="pointer-events-none absolute top-0 right-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(240,160,48,0.12)_0%,transparent_70%)]"
        aria-hidden
      />
      <div className="relative z-10 space-y-4">
        <div>
          <p className="text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">Brand</p>
          <p className="text-sm font-bold tracking-wide text-[#f5f5f0]">{brandDisplayName(brand)}</p>
        </div>
        <div>
          <p className="text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
            Big brand idea
          </p>
          <h2 className="font-display text-3xl font-black tracking-tight text-[#f5f5f0] md:text-4xl">
            {bigIdeaName}
          </h2>
          {belief ? (
            <p className="mt-2 text-sm text-[#8a8a8a] italic">&quot;{belief}&quot;</p>
          ) : null}
        </div>
        <div>
          <p className="mb-3 text-[11px] font-bold tracking-widest text-[#f0a030] uppercase">
            The Stick Standard — runs every week, not just one month
          </p>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {STICK_STANDARD.map((row) => (
              <p key={row.key} className="text-sm text-[#f5f5f0]">
                <span className={`font-bold ${row.color}`}>{row.key}</span> · {row.text}
              </p>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
