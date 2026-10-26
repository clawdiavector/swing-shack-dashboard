/** What a header brand pick should do. `rescope` reloads the page without a new server select. */
export type BrandPickPlan = 'noop' | 'rescope' | 'select'

/**
 * Stick ↔ Swing Shack is `select`. All brands → the brand already active on
 * the server is `rescope`: the id did not change, but the open page still
 * has to reload. Picking the brand that is already showing is `noop`.
 */
export function planBrandPick(
  currentId: string | undefined,
  isAll: boolean,
  nextId: string,
): BrandPickPlan {
  if (nextId === currentId && !isAll) return 'noop'
  if (nextId === currentId) return 'rescope'
  return 'select'
}
