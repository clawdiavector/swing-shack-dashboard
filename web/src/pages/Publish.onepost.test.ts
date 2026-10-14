import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { publishDispatchNow } from '../lib/api'
import { groupSandboxRowsByPostId, idempotencyKeysForGroup } from '../lib/publishPostGroup'
import type { SandboxQueueItem } from '../lib/api'

describe('Publish page — one post, all keys', () => {
  const rows: SandboxQueueItem[] = [
    { post_id: 'asset-1', idempotency_key: 'qc-asset-1-instagram', human_approved: true },
    { post_id: 'asset-1', idempotency_key: 'qc-asset-1-facebook', human_approved: true },
  ]

  it('groups sandbox rows by post_id for a single Publish now action', () => {
    const groups = groupSandboxRowsByPostId(rows)
    expect(groups).toHaveLength(1)
    expect(idempotencyKeysForGroup(groups[0])).toEqual(['qc-asset-1-instagram', 'qc-asset-1-facebook'])
  })

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? '{}'))
        return {
          status: 200,
          ok: true,
          json: async () => ({ ok: true, body }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('publishDispatchNow posts idempotency_keys for the whole post', async () => {
    const keys = idempotencyKeysForGroup(groupSandboxRowsByPostId(rows)[0])
    await publishDispatchNow(keys)
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalled()
    const init = fetchMock.mock.calls[0][1]
    const body = JSON.parse(String(init?.body))
    expect(body.idempotency_keys).toEqual(keys)
  })
})
