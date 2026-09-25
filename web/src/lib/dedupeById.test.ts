import { describe, expect, it } from 'vitest'
import { dedupeById } from './dedupeById'

describe('dedupeById', () => {
  it('keeps first occurrence when ids repeat (all-brands race)', () => {
    const first = { id: 'draft-1', brand_id: 'swing-shack', title: 'A' }
    const dupe = { id: 'draft-1', brand_id: 'stick', title: 'B' }
    const out = dedupeById([first, dupe, { id: 'draft-2', brand_id: 'bag-drop' }])
    expect(out).toHaveLength(2)
    expect(out[0]).toBe(first)
  })
})
