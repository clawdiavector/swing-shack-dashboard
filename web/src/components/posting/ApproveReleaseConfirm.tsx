import { createPortal } from 'react-dom'
import { postingChannelLabel } from '../../lib/postingWeek'

/** Kyle: one outward-facing release confirm; delete this file + imports to revert Review to content-only approve. */
export function releaseConfirmMessage(channels: string[]): string {
  const names = channels.map((c) => postingChannelLabel(c) ?? c).join(', ')
  return `Release this post to ${names}? This approves delivery to those platforms.`
}

export function ApproveReleaseConfirmDialog({
  open,
  channels,
  onCancel,
  onConfirm,
  busy,
}: {
  open: boolean
  channels: string[]
  onCancel: () => void
  onConfirm: () => void
  busy?: boolean
}) {
  if (!open || typeof document === 'undefined') return null
  // Portal to <body>: inside a card with a transform, `fixed` is relative to the card and the
  // Release button lands off-screen.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="approve-release-title"
      data-testid="approve-release-dialog"
    >
      <div className="max-w-md rounded-2xl border border-bd bg-bg p-5 shadow-xl">
        <h3 id="approve-release-title" className="font-display text-lg font-semibold text-tx">
          Approve &amp; release
        </h3>
        <p className="mt-2 text-sm text-tx2">{releaseConfirmMessage(channels)}</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="rounded-full border border-bd px-4 py-1.5 text-sm font-semibold text-tx2"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="approve-release-confirm"
            className="rounded-full bg-ac px-4 py-1.5 text-sm font-semibold text-bg disabled:opacity-40"
            onClick={onConfirm}
            disabled={busy || channels.length === 0}
          >
            Release
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
