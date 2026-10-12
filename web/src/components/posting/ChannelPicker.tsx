export type ChannelPickerProps = {
  available: string[]
  comingSoon?: string[]
  picked: string[]
  locked?: boolean
  onChange?: (next: string[]) => void
}

const LABELS: Record<string, string> = {
  instagram: 'Instagram',
  facebook: 'Facebook',
  gbp: 'Google Business',
  youtube: 'YouTube',
  tiktok: 'TikTok',
}

export function ChannelPicker({
  available,
  comingSoon = ['youtube', 'tiktok'],
  picked,
  locked = false,
  onChange,
}: ChannelPickerProps) {
  const toggle = (ch: string) => {
    if (locked || comingSoon.includes(ch)) return
    const set = new Set(picked)
    if (set.has(ch)) {
      if (set.size <= 1) return
      set.delete(ch)
    } else {
      set.add(ch)
    }
    onChange?.([...set])
  }

  return (
    <div className="flex flex-wrap gap-2" data-testid="channel-picker">
      {available.map((ch) => {
        const on = picked.includes(ch)
        return (
          <button
            key={ch}
            type="button"
            disabled={locked}
            aria-pressed={on}
            data-channel={ch}
            className={on ? 'chip chip-on' : 'chip'}
            onClick={() => toggle(ch)}
          >
            {LABELS[ch] ?? ch}
          </button>
        )
      })}
      {comingSoon.map((ch) => (
        <button key={ch} type="button" disabled className="chip chip-disabled" data-channel={ch}>
          {LABELS[ch] ?? ch} (coming later)
        </button>
      ))}
    </div>
  )
}
