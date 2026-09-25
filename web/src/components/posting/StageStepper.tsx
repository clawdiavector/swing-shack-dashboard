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
      className="flex min-w-0 flex-nowrap items-end gap-0"
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
                className={`mb-[5px] mx-px h-px w-2 shrink-0 sm:w-2.5 ${
                  lineDone ? 'bg-ac/70' : 'bg-bd'
                }`}
                aria-hidden
              />
            ) : null}
            <div className="flex w-[3.25rem] flex-col items-center gap-1 sm:w-[3.5rem]">
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
                className={`max-w-[4.5rem] text-center text-[10px] leading-tight sm:text-xs ${
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
