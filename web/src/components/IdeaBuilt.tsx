import type { Fleshed } from '../lib/mailIntake'

// An idea built out: the concept, what is on offer, the content, the shots and the next steps.
// Plain text only. Written by a model from the idea and the brand's verified facts, so it says so.

const head = 'text-[11px] font-bold tracking-widest text-tx3 uppercase'

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div>
      <p className={head}>{title}</p>
      <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-xs text-tx2">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  )
}

export function IdeaBuilt({ f }: { f: Fleshed }) {
  return (
    <div className="space-y-3 rounded-lg border border-bd bg-white/5 p-3" data-testid="idea-built">
      <div>
        <p className={head}>Suggested idea</p>
        <p className="font-display text-base font-semibold text-tx">{f.concept.name}</p>
        <p className="text-sm text-tx">{f.concept.one_line}</p>
        {f.concept.why_it_works ? <p className="mt-0.5 text-xs text-tx2">{f.concept.why_it_works}</p> : null}
        {f.concept.audience ? (
          <p className="mt-0.5 text-xs text-tx2">
            <b className="text-tx">For:</b> {f.concept.audience}
          </p>
        ) : null}
      </div>
      {f.offer.what ? (
        <div>
          <p className={head}>The offer</p>
          <p className="text-xs text-tx2">{f.offer.what}</p>
          <List title="Confirm before anything is made" items={f.offer.to_confirm} />
        </div>
      ) : null}
      {f.content.length ? (
        <div>
          <p className={head}>Content</p>
          <ul className="mt-0.5 space-y-1 text-xs text-tx2">
            {f.content.map((c, i) => (
              <li key={i}>
                <b className="text-tx">
                  {c.kind}: {c.title}.
                </b>{' '}
                {c.idea} {c.caption_direction ? <span className="text-tx3">Caption: {c.caption_direction}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <List title="Shots to capture" items={f.shots} />
      {f.next_steps.length ? (
        <div>
          <p className={head}>Next steps</p>
          <ol className="mt-0.5 list-decimal space-y-0.5 pl-4 text-xs text-tx2">
            {f.next_steps.map((s, i) => (
              <li key={i}>
                {s.step} <span className="text-tx3">({s.who})</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      <List title="Questions for Herman" items={f.questions} />
      <List title="Watch out for" items={f.risks} />
      <p className="text-[11px] text-tx3">
        Written by Claude from Herman&rsquo;s idea and the brand&rsquo;s verified facts. Check it before using it.
        Amounts are left to confirm.
      </p>
    </div>
  )
}
