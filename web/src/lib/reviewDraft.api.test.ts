import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  draftRecompose,
  draftRegeneratePhoto,
  draftSwapCandidate,
  inboxAction,
} from './api'

describe('P4 draft review API client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POSTs regenerate with note to /api/drafts/.../regenerate', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, enqueued: ['draft_photo'] }),
    } as Response)
    const result = await draftRegeneratePhoto('draft_asset:c:a', 'fix lighting')
    expect(result.ok).toBe(true)
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/drafts/draft_asset%3Ac%3Aa/regenerate')
    expect(url).not.toContain('/api/image/')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body)).note).toBe('fix lighting')
  })

  it('POSTs recompose headline to /api/drafts/.../recompose', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, composed: { instagram: '/u/ig.png' } }),
    } as Response)
    await draftRecompose('draft_asset:c:a', { headline: 'New hook' })
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/recompose')
    expect(JSON.parse(String(init.body)).headline).toBe('New hook')
  })

  it('POSTs swap with candidate_index', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    } as Response)
    await draftSwapCandidate('draft_asset:c:a', 1)
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/swap')
    expect(JSON.parse(String(init.body)).candidate_index).toBe(1)
  })

  it('POSTs inbox reject with reason body', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    } as Response)
    await inboxAction('draft_asset:c:a', 'reject', 'off brand')
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(init.body)).reason).toBe('off brand')
  })

  it('POSTs inbox approve', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    } as Response)
    await inboxAction('draft_asset:c:a', 'approve')
    const [url] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/approve')
  })
})
