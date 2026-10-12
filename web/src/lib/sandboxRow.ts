import type { SandboxQueueItem } from './api'

export function sandboxRowId(row: SandboxQueueItem): string {
  return String(row.idempotency_key || row.queue_id || '')
}

export function matchSandboxRow(row: SandboxQueueItem, id: string): boolean {
  if (!id) return false
  return String(row.idempotency_key || '') === id || String(row.queue_id || '') === id
}

export function sandboxTitle(row: SandboxQueueItem): string {
  const lodged = String(row.lodged_title || '').trim()
  if (lodged) return lodged.slice(0, 120)
  const caption = String(row.caption || row.caption_preview || '').trim()
  if (caption) return caption.slice(0, 120)
  return `Sandbox ${row.platform || 'post'} — ${row.brand_id || 'brand'}`
}

export function sandboxGoesOutIso(row: SandboxQueueItem): string | null {
  const raw = row.would_publish_at || row.event_date
  if (!raw) return null
  const s = String(raw).trim()
  return s || null
}

export type SandboxQueueGroup = {
  key: string
  rows: SandboxQueueItem[]
}

/** One card per post (asset), not per platform row. */
export function groupSandboxQueue(rows: SandboxQueueItem[]): SandboxQueueGroup[] {
  const map = new Map<string, SandboxQueueItem[]>()
  for (const row of rows) {
    const aid = String(row.asset_id ?? '').trim()
    const key = aid
      ? `${String(row.brand_id ?? '').trim()}:${aid}`
      : sandboxRowId(row) || sandboxTitle(row)
    const bucket = map.get(key)
    if (bucket) bucket.push(row)
    else map.set(key, [row])
  }
  return [...map.entries()].map(([key, grouped]) => ({ key, rows: grouped }))
}

export function sandboxGroupPlatforms(rows: SandboxQueueItem[]): string {
  const platforms = [...new Set(rows.map((r) => String(r.platform || 'post').trim()).filter(Boolean))]
  return platforms.join(' · ')
}

export function sandboxGroupIdempotencyKeys(rows: SandboxQueueItem[]): string[] {
  return rows.map((r) => String(r.idempotency_key ?? '').trim()).filter(Boolean)
}
