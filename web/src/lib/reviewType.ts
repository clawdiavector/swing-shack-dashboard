import type { InboxItem } from './api'
import { channelsPickedSummary } from './postingWeek'

export type ReviewTypeInfo = { label: string; approveMeans: string; noun: string }

export const REVIEW_TYPES: Record<string, ReviewTypeInfo> = {
  calendar_candidate: {
    label: 'Proposed calendar moment',
    noun: 'proposed moment',
    approveMeans: 'Approve keeps this on the calendar. It does not post.',
  },
  draft_asset: {
    label: 'Draft post',
    noun: 'draft post',
    approveMeans: 'Approve marks the draft approved. It does not go live.',
  },
  publish_request: {
    label: 'Ready to release',
    noun: 'post',
    approveMeans: 'Approve releases this post to every picked platform.',
  },
  proposal: {
    label: 'Proposal',
    noun: 'proposal',
    approveMeans: 'Approve accepts the proposal. It does not post.',
  },
}

function titleCase(raw: string) {
  return raw
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

export function publishRequestListMeta(item: InboxItem): string {
  const picked = item.meta?.channels_picked ?? item.meta?.publish_targets
  const summary = channelsPickedSummary(picked)
  return summary ? `Ready to release · ${summary}` : 'Ready to release'
}

export function reviewType(raw?: string): ReviewTypeInfo {
  const key = (raw || '').toLowerCase()
  if (key && REVIEW_TYPES[key]) return REVIEW_TYPES[key]
  const label = raw ? titleCase(raw) : 'Item'
  return {
    label,
    noun: label.toLowerCase(),
    approveMeans: 'Approve records your decision. It does not publish.',
  }
}
