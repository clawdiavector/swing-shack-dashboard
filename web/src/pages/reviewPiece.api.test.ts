import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enqueueOpsQueue, inboxEdit } from '../lib/api'

describe('review piece caption save', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, changed: ['caption'] }),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('PATCHes unified inbox edit with caption body', async () => {
    const result = await inboxEdit('draft_asset:c:a', { caption: 'Updated line' })
    expect(result.ok).toBe(true)
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/inbox/unified/draft_asset%3Ac%3Aa/edit')
    expect(init.method).toBe('PATCH')
    const body = JSON.parse(String(init.body))
    expect(body.caption).toBe('Updated line')
  })
})

describe('review piece regenerate queue', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, id: 'manual-x', action: 'draft_image' }),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POSTs draft_image to ops queue only', async () => {
    await enqueueOpsQueue({
      item_id: 'draft_asset:swing-shack:1',
      action: 'draft_image',
      dedupe_key: 'draft_image-abc',
    })
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/ops/queue')
    expect(url).not.toContain('/api/image/')
    const body = JSON.parse(String(init.body))
    expect(body.action).toBe('draft_image')
    expect(body.item_id).toBe('draft_asset:swing-shack:1')
    expect(body.dedupe_key).toBe('draft_image-abc')
  })
})
