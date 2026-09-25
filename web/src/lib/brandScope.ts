import { SCOPE_KEY, filterOperatingBrandIds, isOperatingBrandId } from './brands'

export type BrandScope = 'all' | string

export function readStoredScope(): string | null {
  try {
    return localStorage.getItem(SCOPE_KEY)
  } catch {
    return null
  }
}

export function writeStoredScope(scope: BrandScope) {
  try {
    localStorage.setItem(SCOPE_KEY, scope)
  } catch {
    /* ignore quota / private mode */
  }
}

/** Pure resolver for tests — AC-1 default is `all` when storage empty. */
export function resolveInitialScope(stored: string | null, operatingBrandIds: string[]): BrandScope {
  if (!stored || stored === 'all') return 'all'
  if (isOperatingBrandId(stored) && operatingBrandIds.includes(stored)) return stored
  return 'all'
}

export function scopeBrandIds(scope: BrandScope, operatingBrandIds: string[]): string[] {
  if (scope === 'all') return operatingBrandIds
  return [scope]
}

export function operatingIdsFromRegistry(registryIds: string[]): string[] {
  return filterOperatingBrandIds(registryIds)
}
