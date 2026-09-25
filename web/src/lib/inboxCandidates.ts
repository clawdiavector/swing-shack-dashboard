import type { InboxItem } from './api'

export type InboxSourceFilter = 'all' | 'holiday' | 'scout' | 'interpreter' | 'operator'
export type InboxDateFilter = 'all' | 'has-date' | 'no-date'

const CANDIDATE_TYPES = new Set(['calendar_candidate', 'proposal'])

export function isCandidateItem(item: InboxItem): boolean {
  return CANDIDATE_TYPES.has((item.type || '').toLowerCase())
}

export function candidateSourceTag(item: InboxItem): string {
  const meta = item.meta || {}
  if (meta.created_by === 'holiday_inject' || meta.source_type === 'holiday') return 'holiday'
  if (meta.source_type === 'operator') return 'operator'
  if (item.type === 'proposal' || meta.source_type === 'interpreter') return 'interpreter'
  return 'scout'
}

export function lodgeDisabled(flags: string[] | undefined): boolean {
  return (flags || []).includes('no_date')
}

export function filterInboxCandidates(
  items: InboxItem[],
  source: InboxSourceFilter,
  dateFilter: InboxDateFilter,
): InboxItem[] {
  return items.filter((item) => {
    if (!isCandidateItem(item)) return false
    if (source !== 'all' && candidateSourceTag(item) !== source) return false
    const flags = item.meta?.flags || []
    const hasDate = !flags.includes('no_date') && Boolean(item.meta?.event_date)
    if (dateFilter === 'has-date' && !hasDate) return false
    if (dateFilter === 'no-date' && hasDate) return false
    return true
  })
}
