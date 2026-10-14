import { describe, expect, it } from 'vitest'
import type { SandboxQueueItem } from './api'
import { groupSandboxRowsByPostId, idempotencyKeysForGroup } from './publishPostGroup'

describe('groupSandboxRowsByPostId', () => {
  it('groups rows sharing post_id', () => {
    const rows: SandboxQueueItem[] = [
      { post_id: 'asset-1', idempotency_key: 'qc-asset-1-instagram', platform: 'instagram' },
      { post_id: 'asset-1', idempotency_key: 'qc-asset-1-facebook', platform: 'facebook' },
      { post_id: 'asset-2', idempotency_key: 'qc-asset-2-instagram', platform: 'instagram' },
    ]
    const groups = groupSandboxRowsByPostId(rows)
    expect(groups).toHaveLength(2)
    expect(groups.find((g) => g.postId === 'asset-1')?.rows).toHaveLength(2)
  })

  it('collects all idempotency keys for dispatch-now', () => {
    const rows: SandboxQueueItem[] = [
      { post_id: 'asset-1', idempotency_key: 'qc-asset-1-instagram' },
      { post_id: 'asset-1', idempotency_key: 'qc-asset-1-facebook' },
    ]
    const group = groupSandboxRowsByPostId(rows)[0]
    expect(idempotencyKeysForGroup(group)).toEqual(['qc-asset-1-instagram', 'qc-asset-1-facebook'])
  })
})

