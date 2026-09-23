import { describe, expect, it } from 'vitest'
import { PLATFORM_TABS, resolvePlatformTab } from './platformMock'

describe('resolvePlatformTab', () => {
  it('accepts canonical ids', () => {
    expect(resolvePlatformTab('instagram')).toBe('instagram')
    expect(resolvePlatformTab('facebook')).toBe('facebook')
    expect(resolvePlatformTab('gbp')).toBe('gbp')
  })

  it('accepts aliases case-insensitively', () => {
    expect(resolvePlatformTab('IG')).toBe('instagram')
    expect(resolvePlatformTab('fb')).toBe('facebook')
    expect(resolvePlatformTab('google')).toBe('gbp')
    expect(resolvePlatformTab('GMB')).toBe('gbp')
  })

  it('falls back to instagram for empty or unknown', () => {
    expect(resolvePlatformTab('')).toBe('instagram')
    expect(resolvePlatformTab(undefined)).toBe('instagram')
    expect(resolvePlatformTab('  ')).toBe('instagram')
    expect(resolvePlatformTab('tiktok')).toBe('instagram')
  })
})

describe('PLATFORM_TABS', () => {
  it('lists three platforms', () => {
    expect(PLATFORM_TABS.map((t) => t.id)).toEqual(['instagram', 'facebook', 'gbp'])
  })
})
