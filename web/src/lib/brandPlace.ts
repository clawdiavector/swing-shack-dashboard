// Inbox label for scout suggestions set in another province (campaign-os/_lib/brand_place.py; audit, 3 Nov 2026).

export type FarFromBrand = { place?: string; home?: string } | null

export function farAwayLabel(meta: { far_from_brand?: FarFromBrand } | undefined, brandLabel?: string): string {
  const far = meta?.far_from_brand
  if (!far?.place) return ''
  return `Far away: ${far.place} (${brandLabel || 'the brand'} is in ${far.home})`
}
