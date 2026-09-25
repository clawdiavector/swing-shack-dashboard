import type { InboxItem } from './api'
import { resolveAssetUrl } from './api'

export function draftHeadlineFromCaption(caption?: string): string {
  const line = (caption || '').split('\n').map((s) => s.trim()).find(Boolean)
  return line || ''
}

export function composedChannelKeys(item: InboxItem): string[] {
  const composed = item.meta?.composed
  if (!composed || typeof composed !== 'object') return []
  const keys = Object.keys(composed).filter((k) => Boolean(composed[k]))
  const primary = item.meta?.primary_channel
  if (primary && keys.includes(primary)) {
    return [primary, ...keys.filter((k) => k !== primary)]
  }
  return keys
}

export function composedUrlForChannel(item: InboxItem, channel: string): string {
  const raw = item.meta?.composed?.[channel]
  return raw ? resolveAssetUrl(raw) : ''
}

type DraftQc = NonNullable<NonNullable<InboxItem['meta']>['qc']>

export function qcDisplayScore(qc: DraftQc | undefined) {
  if (!qc || typeof qc !== 'object') return null
  const scores = qc.scores
  if (scores && typeof scores === 'object') {
    const nums = Object.values(scores).filter((v): v is number => typeof v === 'number')
    if (nums.length) {
      const avg = nums.reduce((a, b) => a + b, 0) / nums.length
      return Math.round(avg * 10) / 10
    }
  }
  return null
}

export function qcReasonsList(qc: DraftQc | undefined): string[] {
  if (!qc || typeof qc !== 'object') return []
  const top = Array.isArray(qc.reasons) ? qc.reasons.map(String) : []
  if (top.length) return top
  const sel = qc.selected
  const candidates = Array.isArray(qc.candidates) ? qc.candidates : []
  const row = candidates.find((c) => c && typeof c === 'object' && c.index === sel)
  if (row && Array.isArray(row.reasons)) return row.reasons.map(String)
  return []
}

export function briefSectionEntries(
  sections: NonNullable<NonNullable<InboxItem['meta']>['brief']>['sections'],
): Array<{ title: string; body: string }> {
  if (!Array.isArray(sections)) return []
  return sections.map((row, i) => {
    if (typeof row === 'string') {
      return { title: `Section ${i + 1}`, body: row }
    }
    if (row && typeof row === 'object') {
      const title = String(row.title || row.name || `Section ${i + 1}`)
      const body = String(row.body || row.content || '')
      return { title, body }
    }
    return { title: `Section ${i + 1}`, body: '' }
  }).filter((s) => s.body.trim())
}
