import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CampaignAsset, InboxItem } from './api'
import {
  fetchInboxItem,
  inboxMediaTag,
  resolvedInboxVisualUrl,
  reviewPiecePath,
} from './api'

describe('reviewPiecePath', () => {
  it('appends brand query when provided', () => {
    expect(reviewPiecePath('draft_asset:a:b', 'swing-shack')).toBe(
      '/review/draft_asset%3Aa%3Ab?brand=swing-shack',
    )
  })

  it('omits brand query when absent', () => {
    expect(reviewPiecePath('x')).toBe('/review/x')
  })
})

describe('fetchInboxItem', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          items: [{ id: 'draft_asset:swing-shack:1', brand_id: 'swing-shack' }],
        }),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses one status=all unified fetch scoped by brand', async () => {
    const item = await fetchInboxItem('draft_asset:swing-shack:1', 'swing-shack')
    expect(item?.id).toBe('draft_asset:swing-shack:1')
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/api/inbox/unified?')
    expect(url).toContain('status=all')
    expect(url).toContain('brand=swing-shack')
    expect(url).not.toContain('status=pending')
  })
})

describe('resolvedInboxVisualUrl', () => {
  const item: InboxItem = {
    id: 'draft_asset:x:y',
    type: 'draft_asset',
    meta: {},
  }

  it('prefers campaign asset URL over empty meta', () => {
    const asset: CampaignAsset = { visualUrl: 'https://cdn.example/a.png' }
    expect(resolvedInboxVisualUrl(item, asset)).toBe('https://cdn.example/a.png')
  })

  it('falls back to meta thumb when asset has no visual', () => {
    const withMeta: InboxItem = {
      ...item,
      meta: { image_url: 'https://cdn.example/b.png' },
    }
    expect(resolvedInboxVisualUrl(withMeta, null)).toBe('https://cdn.example/b.png')
  })
})

describe('inboxMediaTag', () => {
  it('downgrades to no-image when visual is broken', () => {
    const item: InboxItem = {
      id: 'x',
      type: 'draft_asset',
      meta: { image_url: 'https://dead.example/x.png' },
    }
    const tag = inboxMediaTag(item, { visualBroken: true })
    expect(tag.id).toBe('no-image')
  })
})
