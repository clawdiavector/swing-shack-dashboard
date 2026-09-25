import { Check } from 'lucide-react'
import {
  firstIncompleteStageFromStages,
  POSTING_STAGE_LABELS,
  POSTING_STAGE_ORDER,
  type PostingStageKey,
} from '../../lib/postingWeek'

export function StageStepper({ stages }: { stages: Record<string, boolean> }) {
  const current = firstIncompleteStageFromStages(stages)
  return (
    <div
      className="flex min-w-0 flex-wrap items-start gap-y-2 pt-2"
      role="list"
      aria-label="Posting pipeline"
    >
      {POSTING_STAGE_ORDER.map((key, index) => {
        const done = Boolean(stages[key])
        const isCurrent = !done && key === current
        const lineDone =
          index > 0 &&
          POSTING_STAGE_ORDER.slice(0, index).every((prev) => Boolean(stages[prev]))
        return (
          <div key={key} className="flex min-w-0 items-center" role="listitem">
            {index > 0 ? (
              <span
                className={`mx-0.5 hidden h-px w-3 shrink-0 sm:block ${
                  lineDone ? 'bg-ac/70' : 'bg-bd'
                }`}
                aria-hidden
              />
            ) : null}
            <div className="flex min-w-[3.25rem] flex-col items-center gap-1 px-0.5">
              <span
                className={`flex h-2.5 w-2.5 shrink-0 items-center justify-center rounded-full ${
                  done
                    ? 'bg-ac text-bg'
                    : isCurrent
                      ? 'border-2 border-ac bg-bg-2 ring-2 ring-ac/25'
                      : 'border border-bd bg-transparent'
                }`}
                aria-hidden
              >
                {done ? <Check className="h-1.5 w-1.5" strokeWidth={3} /> : null}
              </span>
              <span
                className={`max-w-[4.5rem] text-center text-xs leading-tight ${
                  done ? 'font-medium text-tx' : isCurrent ? 'font-semibold text-tx' : 'text-tx3'
                }`}
              >
                {POSTING_STAGE_LABELS[key as PostingStageKey]}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
