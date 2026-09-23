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
