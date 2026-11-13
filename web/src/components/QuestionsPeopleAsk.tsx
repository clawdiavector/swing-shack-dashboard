import { Search } from 'lucide-react'
import { useState } from 'react'
import { Tip } from './ui'

export type PeopleAskQuestion = { question: string; from: string }

const FIRST = 10

/**
 * Plan > Ideas: what people type into Google about this brand's topics, as post ideas.
 * The list comes from /api/faq/questions (refreshed weekly). Parking puts the question
 * on the calendar like any other idea.
 */
export function QuestionsPeopleAsk({
  questions,
  error,
  parkLabel,
  busyTitle,
  onPark,
}: {
  questions: PeopleAskQuestion[] | null
  error?: string
  parkLabel: string
  busyTitle: string | null
  onPark: (title: string) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const shown = questions ? (showAll ? questions : questions.slice(0, FIRST)) : []

  return (
    <section className="glass rounded-2xl border border-white/10 p-4 backdrop-blur-xl">
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-yel" strokeWidth={2.5} />
        <h2 className="font-display text-lg font-semibold">Questions people ask Google</h2>
      </div>
      <p className="mt-1 text-sm text-tx3">
        Real searches about what we sell, refreshed weekly. Answer one in a post. Check every fact and price before it goes out.
      </p>

      {questions === null ? (
        <p className="mt-3 text-sm text-tx3">Looking up questions…</p>
      ) : !questions.length ? (
        <p className="mt-3 text-sm text-tx3">{error || 'No questions found this week.'}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {shown.map((q) => (
            <li
              key={q.question}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 px-3 py-2"
            >
              <span>
                <span className="font-semibold text-tx">{q.question}</span>
                <span className="block text-xs text-tx3">Searched: {q.from}</span>
              </span>
              <Tip text={`Park this question on ${parkLabel} as a post idea.`}>
                <button
                  type="button"
                  disabled={busyTitle === q.question}
                  onClick={() => onPark(q.question)}
                  className="rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
                >
                  {busyTitle === q.question ? 'Parking…' : `Park on ${parkLabel}`}
                </button>
              </Tip>
            </li>
          ))}
        </ul>
      )}

      {questions && questions.length > FIRST ? (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 text-sm font-semibold text-ac hover:text-yel"
        >
          {showAll ? 'Show fewer' : `Show all ${questions.length}`}
        </button>
      ) : null}
    </section>
  )
}
