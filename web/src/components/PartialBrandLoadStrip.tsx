import type { FanOutFailure } from '../lib/fanOut'

export function PartialBrandLoadStrip({
  failures,
  onRetry,
}: {
  failures: FanOutFailure[]
  onRetry: () => void
}) {
  if (failures.length === 0) return null
  const names = failures.map((f) => f.brandId.replace(/-/g, ' ')).join(', ')
  return (
    <p className="rounded-2xl border border-yel/40 bg-yel/10 px-4 py-3 text-sm text-yel">
      Couldn&apos;t load {names} — showing the other brand{failures.length > 1 ? 's' : ''}.{' '}
      <button type="button" className="font-semibold underline" onClick={onRetry}>
        Retry
      </button>
    </p>
  )
}
