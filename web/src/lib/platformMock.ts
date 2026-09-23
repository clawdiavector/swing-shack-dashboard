export type PlatformTab = 'instagram' | 'facebook' | 'gbp'

export const PLATFORM_TABS: { id: PlatformTab; label: string }[] = [
  { id: 'instagram', label: 'Instagram' },
  { id: 'facebook', label: 'Facebook' },
  { id: 'gbp', label: 'GBP' },
]

const ALIASES: Record<string, PlatformTab> = {
  instagram: 'instagram',
  ig: 'instagram',
  facebook: 'facebook',
  fb: 'facebook',
  gbp: 'gbp',
  google: 'gbp',
  gmb: 'gbp',
  'google-business': 'gbp',
}

export function resolvePlatformTab(raw?: string | null): PlatformTab {
  const key = String(raw ?? '')
    .trim()
    .toLowerCase()
  if (!key) return 'instagram'
  return ALIASES[key] ?? 'instagram'
}
