/** Mirrors `campaign-os/_lib/marketing_calendar.py` VALID_BRAND_IDS */
export const VALID_BRAND_IDS = ['swing-shack', 'stick', 'bag-drop'] as const

export type OperatingBrandId = (typeof VALID_BRAND_IDS)[number]

export const SCOPE_KEY = 'heroes.brandScope'

export function isOperatingBrandId(id: string): id is OperatingBrandId {
  return (VALID_BRAND_IDS as readonly string[]).includes(id)
}

export function filterOperatingBrandIds(ids: string[]): string[] {
  const set = new Set<string>(VALID_BRAND_IDS)
  return ids.filter((id) => set.has(id))
}

export function brandRank(brandId: string, orderedIds: string[]): number {
  const i = orderedIds.indexOf(brandId)
  return i >= 0 ? i : orderedIds.length + 1
}
