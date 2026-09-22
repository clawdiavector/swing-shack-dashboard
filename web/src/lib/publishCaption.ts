/** Display title for publish-queue rows (ported from classic renderPublish pickTitle). */
export function pickQueueTitle(it: Record<string, unknown>): string {
  const raw = String(
    it.caption_preview || it.caption || it.name || it.linked_hook_id || '(no caption)',
  )
  const strip = raw.replace(
    /\n\n[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}]\ufe0f? [A-Z][a-z]+(?: [A-Z][a-z]+)?\n\n/gu,
    '\n\n',
  )
  return strip.replace(/\s+/g, ' ').trim().slice(0, 90)
}

export function matchQueueRow(it: Record<string, unknown>, item: string, asset: string): boolean {
  if (!item && !asset) return false
  const ids = [
    it.item_id,
    it.publish_id,
    it.asset_id,
    (it as { assetId?: string }).assetId,
  ].map((v) => (v != null ? String(v) : ''))
  if (item && ids.includes(item)) return true
  if (asset && ids.includes(asset)) return true
  return false
}
