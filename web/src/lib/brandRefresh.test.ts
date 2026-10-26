import { describe, expect, it } from 'vitest'
import { planBrandPick } from './brandRefresh'

describe('planBrandPick', () => {
  it('selects when switching Stick to Swing Shack', () => {
    expect(planBrandPick('stick', false, 'swing-shack')).toBe('select')
  })

  it('selects when switching Swing Shack to Stick', () => {
    expect(planBrandPick('swing-shack', false, 'stick')).toBe('select')
  })

  it('reloads without a new select when leaving All for the brand already active', () => {
    expect(planBrandPick('stick', true, 'stick')).toBe('rescope')
  })

  it('does nothing when the same brand is picked again', () => {
    expect(planBrandPick('stick', false, 'stick')).toBe('noop')
  })

  it('selects the first brand when none is active yet', () => {
    expect(planBrandPick(undefined, true, 'swing-shack')).toBe('select')
  })
})
