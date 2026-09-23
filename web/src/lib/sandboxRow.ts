import type { SandboxQueueItem } from './api'

export function sandboxRowId(row: SandboxQueueItem): string {
  return String(row.idempotency_key || row.queue_id || '')
}

export function matchSandboxRow(row: SandboxQueueItem, id: string): boolean {
  if (!id) return false
  return String(row.idempotency_key || '') === id || String(row.queue_id || '') === id
}

export function sandboxTitle(row: SandboxQueueItem): string {
  const caption = String(row.caption || row.caption_preview || '').trim()
  if (caption) return caption.slice(0, 120)
  return `Sandbox ${row.platform || 'post'} — ${row.brand_id || 'brand'}`
}
