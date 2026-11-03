import type { MouseEvent } from 'react'
import { publishNowControlText } from '../../lib/publishConfirm'

/** Publish now, with the +5 send time visible before the click. */
export function PublishNowButton({
  disabled,
  onClick,
  now,
  testId,
  className,
}: {
  disabled?: boolean
  onClick: (event: MouseEvent<HTMLButtonElement>) => void
  now?: Date
  testId?: string
  className?: string
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      data-testid={testId}
      onClick={onClick}
      className={
        className ??
        'rounded-full bg-ac px-3 py-1 text-left text-xs font-semibold text-bg disabled:opacity-40'
      }
    >
      <span className="block">Publish now</span>
      <span className="block text-[10px] font-medium leading-snug">{publishNowControlText(now)}</span>
    </button>
  )
}
