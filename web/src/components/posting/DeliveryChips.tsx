import { formatSastClock, postingChannelLabel, deliveryChipLabel, deliveryChipTone, type PostDelivery } from '../../lib/postingWeek'

export type DeliveryChipsProps = {
  deliveries?: PostDelivery[] | null
  brandId?: string
  calendarId?: string
  onRetry?: (channel: string) => void
  onDrop?: (channel: string) => void
  busyChannel?: string
}

function toneClasses(tone: ReturnType<typeof deliveryChipTone>): string {
  switch (tone) {
    case 'ok':
      return 'border-green/40 bg-green/10 text-green'
    case 'bad':
      return 'border-red/40 bg-red/10 text-red'
    case 'gold':
      return 'border-yel/40 bg-yel/10 text-yel'
    case 'warn':
      return 'border-yel/40 bg-yel/5 text-yel'
    default:
      return 'border-bd bg-bg-2/40 text-tx2'
  }
}

export function DeliveryChips({
  deliveries,
  onRetry,
  onDrop,
  busyChannel,
}: DeliveryChipsProps) {
  const rows = (deliveries ?? []).filter((d) => d.status !== 'not_picked' && d.status !== 'skipped')
  if (!rows.length) return null

  return (
    <ul className="flex flex-col gap-2" data-testid="delivery-chips">
      {rows.map((d) => {
        const tone = deliveryChipTone(d.status)
        const label = postingChannelLabel(d.channel) ?? d.channel
        const statusLabel = deliveryChipLabel(d.status)
        const clock = formatSastClock(d.would_publish_at)
        const failed = String(d.status).toLowerCase() === 'failed'
        const err = failed && d.last_error ? String(d.last_error).slice(0, 120) : null
        return (
          <li
            key={d.channel}
            data-testid={`delivery-chip-${d.channel}`}
            className={`rounded-xl border px-3 py-2 text-xs ${toneClasses(tone)}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{label}</span>
              <span className="opacity-90">{statusLabel}</span>
              {clock ? <span className="text-tx3">{clock}</span> : null}
            </div>
            {err ? (
              <p className="mt-1 font-medium leading-snug" data-testid={`delivery-error-${d.channel}`}>
                {err}
              </p>
            ) : null}
            {failed && (onRetry || onDrop) ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {onRetry ? (
                  <button
                    type="button"
                    data-testid={`delivery-retry-${d.channel}`}
                    disabled={busyChannel === d.channel}
                    className="rounded-full border border-current px-2 py-0.5 text-[11px] font-semibold disabled:opacity-40"
                    onClick={() => onRetry(d.channel)}
                  >
                    Retry
                  </button>
                ) : null}
                {onDrop ? (
                  <button
                    type="button"
                    data-testid={`delivery-drop-${d.channel}`}
                    disabled={busyChannel === d.channel}
                    className="rounded-full border border-bd px-2 py-0.5 text-[11px] font-semibold text-tx2 disabled:opacity-40"
                    onClick={() => onDrop(d.channel)}
                  >
                    Drop
                  </button>
                ) : null}
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
