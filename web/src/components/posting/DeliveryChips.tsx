import { deliveryChipLabel, deliveryChipTone } from '../../lib/postingWeek'

export type DeliveryRow = {
  channel: string
  status: string
  last_error?: string | null
}

export type DeliveryChipsProps = {
  deliveries: DeliveryRow[]
  onRetry?: (channel: string) => void
  onDrop?: (channel: string) => void
}

export function DeliveryChips({ deliveries, onRetry, onDrop }: DeliveryChipsProps) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="delivery-chips">
      {deliveries.map((d) => (
        <div key={d.channel} className={`delivery-chip tone-${deliveryChipTone(d.status)}`}>
          <span>{d.channel}</span>
          <span>{deliveryChipLabel(d.status)}</span>
          {d.status === 'failed' && d.last_error ? (
            <span className="delivery-error">{d.last_error}</span>
          ) : null}
          {d.status === 'failed' ? (
            <>
              <button type="button" onClick={() => onRetry?.(d.channel)}>
                Retry
              </button>
              <button type="button" onClick={() => onDrop?.(d.channel)}>
                Drop
              </button>
            </>
          ) : null}
        </div>
      ))}
    </div>
  )
}
