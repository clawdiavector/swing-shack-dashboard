import { describe, expect, it } from 'vitest'
import { cannotSave } from './seoFixer'

describe('cannotSave', () => {
  it('is only true when WordPress said it will not keep the field', () => {
    expect(cannotSave({ writable: false })).toBe(true)
  })

  it('offers Apply when writable, and when WordPress could not be asked', () => {
    expect(cannotSave({ writable: true })).toBe(false)
    expect(cannotSave({ writable: null })).toBe(false)
    expect(cannotSave({})).toBe(false)
  })
})
