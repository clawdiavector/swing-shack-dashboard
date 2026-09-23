import { describe, expect, it } from 'vitest'
import type { SandboxQueueItem } from './api'
import { matchSandboxRow, sandboxRowId, sandboxTitle } from './sandboxRow'

describe('sandboxRowId', () => {
  it('prefers idempotency_key', () => {
    expect(
      sandboxRowId({ idempotency_key: 'qc-a-ig', queue_id: 'uuid-1' } as SandboxQueueItem),
    ).toBe('qc-a-ig')
  })

  it('falls back to queue_id', () => {
    expect(sandboxRowId({ queue_id: 'uuid-1' } as SandboxQueueItem)).toBe('uuid-1')
  })

  it('returns empty when neither set', () => {
    expect(sandboxRowId({} as SandboxQueueItem)).toBe('')
  })
})

describe('matchSandboxRow', () => {
  const row = { idempotency_key: 'qc-a-ig', queue_id: 'uuid-1' } as SandboxQueueItem

  it('matches idempotency_key', () => {
    expect(matchSandboxRow(row, 'qc-a-ig')).toBe(true)
  })

  it('matches queue_id', () => {
    expect(matchSandboxRow(row, 'uuid-1')).toBe(true)
  })

  it('misses empty or foreign id', () => {
    expect(matchSandboxRow(row, '')).toBe(false)
    expect(matchSandboxRow(row, 'other')).toBe(false)
  })
})

describe('sandboxTitle', () => {
  it('uses caption truncated to 120', () => {
    const long = 'x'.repeat(200)
    expect(sandboxTitle({ caption: long } as SandboxQueueItem)).toHaveLength(120)
  })

  it('falls back to platform and brand', () => {
    expect(sandboxTitle({ platform: 'instagram', brand_id: 'swing-shack' } as SandboxQueueItem)).toBe(
      'Sandbox instagram — swing-shack',
    )
  })

  it('uses post and brand defaults', () => {
    expect(sandboxTitle({} as SandboxQueueItem)).toBe('Sandbox post — brand')
  })
})
