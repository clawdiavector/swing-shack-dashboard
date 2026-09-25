import { describe, expect, it } from 'vitest'
import { resolveInitialScope } from './brandScope'

describe('resolveInitialScope', () => {
  const ids = ['swing-shack', 'stick', 'bag-drop']

  it('defaults to all when storage is empty', () => {
    expect(resolveInitialScope(null, ids)).toBe('all')
  })

  it('restores a valid stored brand', () => {
    expect(resolveInitialScope('stick', ids)).toBe('stick')
  })

  it('falls back to all for unknown stored value', () => {
    expect(resolveInitialScope('takomo', ids)).toBe('all')
  })
})
