import { useCallback, useEffect, useState } from 'react'
import {
  fetchMailIntake,
  ideaHeading,
  mailIdeaFlesh,
  mailIdeaPlan,
  markMail,
  moveMail,
  type MailIntake,
  type MailItem,
} from '../lib/mailIntake'
import { brandLabel } from '../lib/planMessages'
import { PlanPanel } from '../pages/calendar/planning/PlanPanel'
import { IdeaBuilt } from './IdeaBuilt'
import { Badge } from './ui'

// Mail to the agent inbox from the CEO, sorted for you. Do now: something to act on. Ideas: one card
// each; "Show proposed plan" makes a draft plan you can edit, then Approve plan and Put on the calendar.
// Shows nothing when the inbox is quiet. Nothing goes on the calendar or is posted until you say so.

const BRANDS = ['stick', 'swing-shack', 'bag-drop']
const field = 'rounded-md border border-bd bg-transparent px-2 py-1 text-xs text-tx'
const btn = 'rounded-full border border-yel/40 bg-yel/20 px-3 py-1 text-xs font-bold text-yel hover:bg-yel/30 disabled:opacity-60'
const quiet = 'text-xs font-semibold text-tx3 hover:text-tx disabled:opacity-60'

type Run = (p: Promise<{ ok: boolean; error?: string }>) => Promise<void>

export function MailToday({ brandId }: { brandId?: string }) {
  const [data, setData] = useState<MailIntake | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    // A failed read means no card: this is an alert, not a page.
    fetchMailIntake(brandId)
      .then(setData)
      .catch(() => setData(null))
  }, [brandId])

  useEffect(load, [load])

  if (!data) return null
  const total = data.do_now.length + data.ideas.length
  if (total === 0 && data.watching.inbox) return null

  const run: Run = async (p) => {
    setError(null)
    const r = await p
    if (!r.ok) setError(r.error || 'That did not work.')
    load()
  }

  return (
    <section
      aria-label="Do now and ideas from the agent inbox"
      className="glass rounded-2xl border-[1.5px] border-red/40 p-4 backdrop-blur-xl"
      data-testid="mail-today"
    >
      {!data.watching.inbox ? (
        <p className="mt-2 text-xs text-yel" data-testid="mail-not-watching">
          Nobody is watching the agent inbox from this server yet, so new mail will not show up here.
        </p>
      ) : null}
      {error ? <p className="mt-2 text-xs text-red">{error}</p> : null}

      {data.do_now.length ? (
        <div className="mt-3 first:mt-0">
          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Do now</h2>
            <Badge tone="red">{data.do_now.length}</Badge>
          </div>
          <ul className="mt-1 space-y-3 text-sm">
            {data.do_now.map((m) => (
              <li key={m.id} data-testid="mail-do-now">
                <MailHead m={m} />
                <div className="mt-1 flex flex-wrap items-center gap-3">
                  <button type="button" className={btn} onClick={() => void run(markMail(m.id, 'done'))}>
                    Done
                  </button>
                  <button type="button" className={quiet} onClick={() => void run(moveMail(m.id, 'idea'))}>
                    It is an idea
                  </button>
                  <button type="button" className={quiet} onClick={() => void run(markMail(m.id, 'dismissed'))}>
                    Dismiss
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {data.ideas.length ? (
        <div className="mt-3 first:mt-0">
          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Ideas</h2>
            <Badge tone="gold">{data.ideas.length}</Badge>
          </div>
          <ul className="mt-2 space-y-3 text-sm">
            {data.ideas.map((m) => (
              <li key={m.id} className="rounded-xl border border-bd p-3" data-testid="mail-idea">
                <IdeaCard m={m} run={run} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function FromNote({ m }: { m: MailItem }) {
  const part = m.idea_total && m.idea_total > 1 ? `, idea ${m.idea_index} of ${m.idea_total}` : ''
  return (
    <span className="text-[11px] text-tx3" data-testid="mail-from">
      from {m.from_name || 'Herman'}
      {part}
      {m.subject ? ` (mail: ${m.subject})` : ''}
    </span>
  )
}

function MailHead({ m }: { m: MailItem }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-tx">{m.subject || '(no subject)'}</span>
        {m.brand ? <Badge tone="blue">{brandLabel(m.brand)}</Badge> : null}
        {m.date ? <span className="text-xs text-tx3">{m.date}</span> : null}
        <FromNote m={{ ...m, subject: '', idea_total: 1 }} />
      </div>
      {m.summary ? <p className="mt-0.5 line-clamp-3 text-xs whitespace-pre-line text-tx2">{m.summary}</p> : null}
    </>
  )
}

function IdeaCard({ m, run }: { m: MailItem; run: Run }) {
  const [brand, setBrand] = useState(m.brand || '')
  const [date, setDate] = useState(m.date || '')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)
  const [writing, setWriting] = useState(false)
  const [showIdea, setShowIdea] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const ready = Boolean(brand && date)
  const changed = Boolean(m.plan_id) && (brand !== (m.brand || '') || date !== (m.date || ''))

  async function showPlan() {
    if (open && !changed) {
      setOpen(false)
      return
    }
    setBusy(true)
    setError(null)
    const r = await mailIdeaPlan(m.id, brand, date, changed)
    setBusy(false)
    if (!r.ok) {
      setError(r.error || 'Could not make the plan.')
      return
    }
    setVersion((v) => v + 1)
    setOpen(true)
    void run(Promise.resolve({ ok: true }))
  }

  async function fleshOut() {
    setWriting(true)
    setError(null)
    const r = await mailIdeaFlesh(m.id, brand, date)
    setWriting(false)
    if (!r.ok) {
      setError(r.error || 'Could not write the idea.')
      return
    }
    setShowIdea(true)
    void run(Promise.resolve({ ok: true }))
  }

  const briefId = m.brief_id || `brf-${m.id}`

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-tx">{ideaHeading(m)}</span>
        <FromNote m={m} />
      </div>
      {m.summary ? <p className="mt-0.5 line-clamp-4 text-xs whitespace-pre-line text-tx2">{m.summary}</p> : null}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select aria-label="Which brand" className={field} value={brand} onChange={(e) => setBrand(e.target.value)}>
          <option value="">Which brand?</option>
          {BRANDS.map((b) => (
            <option key={b} value={b}>
              {brandLabel(b)}
            </option>
          ))}
        </select>
        <input aria-label="Which date" type="date" className={field} value={date} onChange={(e) => setDate(e.target.value)} />
        <button
          type="button"
          className={btn}
          disabled={!brand || writing}
          title={brand ? 'Claude builds the idea out: concept, content, shots and next steps.' : 'Pick the brand first'}
          onClick={() => void fleshOut()}
          data-testid="mail-idea-flesh"
        >
          {writing ? 'Writing…' : m.fleshed ? 'Write it again' : 'Flesh out this idea'}
        </button>
        <button
          type="button"
          className={btn}
          disabled={!ready || busy}
          title={ready ? 'A draft plan you can edit. Nothing goes on the calendar yet.' : 'Pick the brand and the date first'}
          onClick={() => void showPlan()}
          data-testid="mail-idea-show-plan"
        >
          {busy ? 'Making…' : open && !changed ? 'Hide proposed plan' : 'Show proposed plan'}
        </button>
        <button type="button" className={quiet} onClick={() => void run(moveMail(m.id, 'do_now'))}>
          It is a to-do
        </button>
        <button type="button" className={quiet} onClick={() => void run(markMail(m.id, 'dismissed'))}>
          Dismiss
        </button>
      </div>
      {error ? <p className="mt-1 text-xs text-red">{error}</p> : null}
      {m.fleshed ? (
        <div className="mt-3">
          <button type="button" className={quiet} onClick={() => setShowIdea((v) => !v)}>
            {showIdea ? 'Hide the suggested idea' : 'Show the suggested idea'}
          </button>
          {showIdea ? <IdeaBuilt f={m.fleshed} /> : null}
          {m.plan_id ? (
            <p className="mt-1 text-[11px] text-tx3">
              If you rewrite the idea after the plan was made, use Start again in the plan to rebuild it from the idea.
            </p>
          ) : null}
        </div>
      ) : null}
      {error ? <p className="mt-1 text-xs text-red">{error}</p> : null}
      {open && brand && briefId ? (
        <div className="mt-3 rounded-lg border border-bd" data-testid="mail-idea-plan">
          <PlanPanel key={`${briefId}-${version}`} brandId={brand} briefId={briefId} />
        </div>
      ) : null}
    </>
  )
}
