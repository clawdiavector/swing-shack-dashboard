import { describe, expect, it, vi } from 'vitest'
import { catalogPublicUrl, ensurePlanCatalog } from './plan'

describe('plan catalog helpers', () => {
  it('builds a catalog opener URL from origin and pack id', () => {
    expect(catalogPublicUrl('pack-cat-1', 'https://ops.example.com')).toBe(
      'https://ops.example.com/catalog/pack-cat-1',
    )
  })

  it('ensurePlanCatalog posts to the plan catalog route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, pack_id: 'pack-x', counts: { posts: 1, pictures: 0, pictures_yet: 1 } }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const r = await ensurePlanCatalog('stick', 'pln-abc')
    expect(r.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/plan/v1/stick/pln-abc/catalog',
      expect.objectContaining({ method: 'POST' }),
    )
    const write = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText: write } })
    await navigator.clipboard.writeText(catalogPublicUrl('pack-x', 'http://127.0.0.1:8080'))
    expect(write).toHaveBeenCalledWith('http://127.0.0.1:8080/catalog/pack-x')
  })
})
