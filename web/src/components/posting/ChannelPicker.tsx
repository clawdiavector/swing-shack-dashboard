import { postingChannelLabel } from '../../lib/postingWeek'

export type ChannelPickerProps = {
  available: string[]
  coming?: string[]
  picked: string[]
  locked?: boolean
  onChange?: (next: string[]) => void
}

const COMING_LABEL = 'Coming later'

function channelButtonLabel(id: string, coming: boolean): string {
  const label = postingChannelLabel(id) ?? id
  return coming ? `${label} (${COMING_LABEL})` : label
}

export function ChannelPicker({
  available,
  coming = [],
  picked,
  locked = false,
  onChange,
}: ChannelPickerProps) {
  const comingSet = new Set(coming.map((c) => c.toLowerCase()))
  const pickedSet = new Set(picked.map((c) => c.toLowerCase()))
  const allIds = [...available, ...coming.filter((c) => !available.includes(c))]

  function toggle(id: string) {
    if (locked || comingSet.has(id.toLowerCase())) return
    const key = id.toLowerCase()
    const next = pickedSet.has(key)
      ? picked.filter((c) => c.toLowerCase() !== key)
      : [...picked, id]
    if (next.length === 0) return
    onChange?.(next)
  }

  return (
    <div
      className="flex flex-wrap gap-2"
      role="group"
      aria-label="Platforms for this post"
      data-testid="channel-picker"
    >
      {allIds.map((id) => {
        const isComing = comingSet.has(id.toLowerCase())
        const isOn = pickedSet.has(id.toLowerCase())
        const disabled = locked || isComing
        return (
          <button
            key={id}
            type="button"
            data-testid={`channel-picker-${id}`}
            disabled={disabled}
            aria-pressed={isOn}
            title={isComing ? COMING_LABEL : undefined}
            onClick={() => toggle(id)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
              isComing
                ? 'cursor-not-allowed border-bd/60 text-tx3 opacity-60'
                : isOn
                  ? 'border-ac bg-ac/15 text-ac'
                  : 'border-bd text-tx2 hover:border-ac/60'
            } ${locked && !isComing ? 'cursor-default opacity-80' : ''}`}
          >
            {channelButtonLabel(id, isComing)}
          </button>
        )
      })}
      {!locked && picked.length === 0 ? (
        <p className="w-full text-xs text-red" data-testid="channel-picker-empty">
          Pick at least one platform.
        </p>
      ) : null}
    </div>
  )
}
