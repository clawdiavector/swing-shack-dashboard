import type { SandboxQueueItem } from './api'
import { sandboxRowId } from './sandboxRow'

export type SandboxPostGroup = {
  postId: string
  rows: SandboxQueueItem[]
  brand_id?: string
}

/** Group sandbox queue rows by post_id (fallback: idempotency_key per row). */
export function groupSandboxRowsByPostId(items: SandboxQueueItem[]): SandboxPostGroup[] {
  const map = new Map<string, SandboxQueueItem[]>()
  for (const row of items) {
    const postId =
      String(row.post_id || '').trim() ||
      String(row.asset_id || '').trim() ||
      sandboxRowId(row) ||
      'unknown'
    const list = map.get(postId) ?? []
    list.push(row)
    map.set(postId, list)
  }
  return [...map.entries()].map(([postId, rows]) => ({
    postId,
    rows,
    brand_id: rows[0]?.brand_id,
  }))
}

export function idempotencyKeysForGroup(group: SandboxPostGroup): string[] {
  return group.rows
    .map((row) => String(row.idempotency_key || '').trim())
    .filter(Boolean)
}
