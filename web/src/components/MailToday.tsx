import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchMailIntake, mailToCalendar, markMail, moveMail, type MailIntake, type MailItem } from '../lib/mailIntake'
import { brandLabel } from '../lib/planMessages'
import { Badge } from './ui'

// Mail to the agent inbox from the CEO, sorted for you. Do now: something to act on. Idea: goes on the
// calendar as a faded suggestion, where Approve and Make a plan already work. Shows nothing when
// the inbox is quiet. Nothing is posted from here.

const BRANDS = ['stick', 'swing-shack', 'bag-drop']
const field = 'rounded-md border border-bd bg-transparent px-2 py-1 text-xs text-tx'
const btn = 'rounded-full border border-yel/40 bg-yel/20 px-3 py-1 text-xs font-bold text-yel hover:bg-yel/30 disabled:opacity-60'
const quiet = 'text-xs font-semibold text-tx3 hover:text-tx disabled:opacity-60'

type Run = (p: Promise<{ ok: boolean; error?: string }>) => Promise<void>

function monthHref(date: string | null) {
  return `/calendar/lanes?tab=month${date ? `&month=${date.slice(0, 7)}` : ''}`
}

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
          <ul className="mt-1 space-y-3 text-sm">
            {data.ideas.map((m) => (
              <li key={m.id} data-testid="mail-idea">
                <MailHead m={m} />
                <IdeaActions m={m} run={run} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function MailHead({ m }: { m: MailItem }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-tx">{m.subject || '(no subject)'}</span>
        {m.brand ? <Badge tone="blue">{brandLabel(m.brand)}</Badge> : null}
        {m.date ? <span className="text-xs text-tx3">{m.date}</span> : null}
        <span className="text-[11px] text-tx3" data-testid="mail-from">
          from {m.from_name || 'Herman'}
        </span>
      </div>
      {m.summary ? <p className="mt-0.5 line-clamp-3 text-xs whitespace-pre-line text-tx2">{m.summary}</p> : null}
    </>
  )
}

function IdeaActions({ m, run }: { m: MailItem; run: Run }) {
  const [brand, setBrand] = useState(m.brand || '')
  const [date, setDate] = useState(m.date || '')

  if (m.calendar_id) {
    return (
      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs">
        <span className="text-emerald-400">On the calendar as a faded suggestion.</span>
        <Link to={monthHref(m.date)} className="font-bold text-ac hover:underline" data-testid="mail-idea-open">
          Open it to Approve
        </Link>
        <button type="button" className={quiet} onClick={() => void run(markMail(m.id, 'done'))}>
          Got it
        </button>
      </div>
    )
  }

  const ready = Boolean(brand && date)
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
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
        disabled={!ready}
        title={ready ? undefined : 'Pick the brand and the date first'}
        onClick={() => void run(mailToCalendar(m.id, brand, date))}
        data-testid="mail-idea-to-calendar"
      >
        Put on the calendar
      </button>
      <button type="button" className={quiet} onClick={() => void run(moveMail(m.id, 'do_now'))}>
        It is a to-do
      </button>
      <button type="button" className={quiet} onClick={() => void run(markMail(m.id, 'dismissed'))}>
        Dismiss
      </button>
    </div>
  )
}
