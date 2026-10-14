export type VisualGapInfo = {
  reason?: string
  label?: string
  post_type?: string
  archetype_id?: string | null
}

function gapFixHint(reason?: string): string {
  switch (reason) {
    case 'no_layout':
    case 'layout_not_vetted':
    case 'oneshot_generated':
      return 'Build a vetted template'
    case 'no_real_photo':
    case 'generated_background_not_allowed':
      return 'Add a real photo'
    default:
      return 'Fix visual trust gate'
  }
}

export function GapTile({
  gap,
  compact = false,
  onRecheck,
  recheckBusy = false,
}: {
  gap?: VisualGapInfo | null
  compact?: boolean
  onRecheck?: () => void
  recheckBusy?: boolean
}) {
  const label = String(gap?.label ?? 'Visual gap').trim()
  const hint = gapFixHint(gap?.reason)

  return (
    <div
      className={`flex w-full flex-col items-center justify-center gap-2 border border-dashed border-yel/50 bg-bg2/40 text-center ${
        compact ? 'aspect-[4/5] rounded-xl px-2 py-3' : 'min-h-[280px] rounded-2xl px-4 py-8 md:min-h-[480px]'
      }`}
      data-testid="gap-tile"
    >
      <p className={`font-semibold leading-snug text-yel ${compact ? 'text-[11px]' : 'text-sm md:text-base'}`}>
        {label}
      </p>
      <p className={`text-tx3 ${compact ? 'text-[10px]' : 'text-xs'}`}>{hint}</p>
      {onRecheck ? (
        <button
          type="button"
          data-testid="gap-recheck-btn"
          disabled={recheckBusy}
          onClick={(e) => {
            e.stopPropagation()
            e.preventDefault()
            onRecheck()
          }}
          className={`rounded-full border border-yel/50 px-2 py-0.5 font-semibold text-yel hover:bg-yel/10 disabled:opacity-50 ${
            compact ? 'text-[10px]' : 'text-xs'
          }`}
        >
          {recheckBusy ? 'Checking…' : 'Re-check'}
        </button>
      ) : null}
    </div>
  )
}
