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
      className="flex min-w-max flex-nowrap items-end gap-0 px-0.5"
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
          <div key={key} className="flex min-w-0 items-end" role="listitem">
            {index > 0 ? (
              <span
                className={`mb-[7px] mx-0.5 h-0.5 w-4 shrink-0 sm:w-5 ${
                  lineDone ? 'bg-ac/70' : 'bg-bd'
                }`}
                aria-hidden
              />
            ) : null}
            <div className="flex w-[4.25rem] flex-col items-center gap-1.5 sm:w-[4.75rem]">
              <span
                className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full ${
                  done
                    ? 'bg-ac text-bg'
                    : isCurrent
                      ? 'border-2 border-ac bg-bg-2 ring-2 ring-ac/25'
                      : 'border border-bd bg-transparent'
                }`}
                aria-hidden
              >
                {done ? <Check className="h-2 w-2" strokeWidth={3} /> : null}
              </span>
              <span
                className={`max-w-[5rem] text-center text-[11px] leading-snug sm:text-xs ${
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
