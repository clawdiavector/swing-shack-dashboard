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
    label: 'Ready to queue',
    noun: 'publish request',
    approveMeans:
      'Approve lets the publish job pick this up — sandbox until live mode is on.',
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
