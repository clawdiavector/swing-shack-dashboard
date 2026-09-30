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

  it('uses lookup then status=all unified fetch scoped by brand', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: async () => ({ ok: false, item: null }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({
            items: [{ id: 'draft_asset:swing-shack:1', brand_id: 'swing-shack' }],
          }),
        }),
    )
    const item = await fetchInboxItem('draft_asset:swing-shack:1', 'swing-shack')
    expect(item?.id).toBe('draft_asset:swing-shack:1')
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const lookupUrl = String(fetchMock.mock.calls[0]?.[0])
    expect(lookupUrl).toContain('/api/inbox/unified/draft_asset%3Aswing-shack%3A1')
    const listUrl = String(fetchMock.mock.calls[1]?.[0])
    expect(listUrl).toContain('/api/inbox/unified?')
    expect(listUrl).toContain('status=all')
    expect(listUrl).toContain('brand=swing-shack')
  })

  it('falls back to publish_request when draft_asset id missing from list', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: async () => ({ ok: false }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              {
                id: 'publish_request:qc-draft-x-instagram',
                type: 'publish_request',
                meta: { asset_id: 'draft-x' },
              },
            ],
          }),
        }),
    )
    const item = await fetchInboxItem('draft_asset:cos-drafts-stick:draft-x', 'stick')
    expect(item?.id).toBe('publish_request:qc-draft-x-instagram')
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

  it('prefers composed channel URL over raw asset visual', () => {
    const withComposed: InboxItem = {
      ...item,
      meta: {
        primary_channel: 'instagram',
        image_url: 'https://cdn.example/raw-gen.png',
        composed: { instagram: 'https://cdn.example/composed.png' },
      },
    }
    const asset: CampaignAsset = { visualUrl: 'https://cdn.example/raw-gen.png' }
    expect(resolvedInboxVisualUrl(withComposed, asset)).toBe('https://cdn.example/composed.png')
  })

  it('hides raw gen when compose_pending', () => {
    const pending: InboxItem = {
      ...item,
      meta: {
        compose_pending: true,
        image_url: 'https://cdn.example/raw-gen.png',
      },
    }
    expect(resolvedInboxVisualUrl(pending, null)).toBe('')
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
