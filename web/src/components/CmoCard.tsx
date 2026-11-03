import type { CmoBrief } from '../lib/api'

const TONE: Record<CmoBrief['verdict']['tone'], string> = {
  act: 'border-red/50',
  watch: 'border-yel/50',
  good: 'border-ac/40',
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold text-tx">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-tx2">
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  )
}

/** The CMO brief at the top of the Reports page: where we stand, what to decide, who does what next. */
export function CmoCard({ cmo }: { cmo?: CmoBrief | null }) {
  if (!cmo) return null
  return (
    <section className={`glass space-y-4 rounded-2xl border p-4 ${TONE[cmo.verdict.tone] ?? 'border-bd/60'}`}>
      <div>
        <p className="text-xs uppercase tracking-wide text-tx3">{cmo.week?.current ?? 'This week'}</p>
        <h2 className="font-display text-lg font-semibold">Where to go</h2>
        <p className="mt-1 text-base font-semibold text-tx">{cmo.verdict.headline}</p>
        {cmo.verdict.lines.map((l, i) => (
          <p key={i} className="mt-1 text-sm text-tx2">
            {l}
          </p>
        ))}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {cmo.numbers.map((n) => (
          <div key={n.label} className="rounded-xl border border-white/10 px-3 py-2">
            <p className="text-xs text-tx3">{n.label}</p>
            <p className="font-display text-xl font-semibold text-tx">{n.value}</p>
            <p className="text-xs text-tx2">{n.vs}</p>
            {n.note ? <p className="text-xs text-tx3">{n.note}</p> : null}
          </div>
        ))}
      </div>

      {cmo.decisions.length ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-tx">Decisions for this week</h3>
          {cmo.decisions.map((d) => (
            <div key={d.decision} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
              <p className="font-semibold text-tx">{d.decision}</p>
              <p className="mt-1 text-tx2">
                <span className="font-semibold text-tx">Recommendation:</span> {d.recommendation}
              </p>
              <p className="mt-1 text-tx2">
                <span className="font-semibold text-tx">Because:</span> {d.because}
              </p>
              <p className="mt-1 text-xs text-tx3">Confidence: {d.confidence}</p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <List title="What is working" items={cmo.working} />
        <List title="What is not" items={cmo.not_working} />
      </div>
      <List title="Risks" items={cmo.risks} />
      <List title="What we cannot see yet" items={cmo.gaps} />
      <List title="Next week" items={cmo.next_week} />
    </section>
  )
}
