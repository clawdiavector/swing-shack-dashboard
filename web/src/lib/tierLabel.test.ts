import { describe, expect, it } from 'vitest'
import { tierLabel } from './planning'

describe('tierLabel', () => {
  it('shows the stored pin tiers as Major, Medium and Light', () => {
    expect(tierLabel('A-PIN')).toBe('Major')
    expect(tierLabel('B-PIN')).toBe('Medium')
    expect(tierLabel('C-PIN')).toBe('Light')
  })

  it('passes an unknown tier through and shows a dash for none', () => {
    expect(tierLabel('WATCH')).toBe('WATCH')
    expect(tierLabel('')).toBe('—')
    expect(tierLabel(undefined)).toBe('—')
  })
})
