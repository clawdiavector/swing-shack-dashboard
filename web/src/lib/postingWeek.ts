export type PostingStageKey =
  | 'booked'
  | 'caption'
  | 'image'
  | 'in_review'
  | 'approved'
  | 'queued'
  | 'released'
  | 'posted'

export type PostState =
  | 'candidate'
  | 'booked'
  | 'drafting'
  | 'needs_fix'
  | 'draft_ready'
  | 'scheduled'
  | 'released'
  | 'posted'

export type PostFlag = 'no_date' | 'no_channel' | 'stale' | 'holiday' | 'operator'

export const POSTING_STAGE_ORDER: PostingStageKey[] = [
  'booked',
  'caption',
  'image',
  'in_review',
  'approved',
  'queued',
  'released',
  'posted',
]

export const POSTING_STAGE_LABELS: Record<PostingStageKey, string> = {
  booked: 'Booked',
  caption: 'Caption',
  image: 'Image',
  in_review: 'In review',
  approved: 'Approved',
  queued: 'Queued',
  released: 'Released',
  posted: 'Posted',
}

export const POST_STATE_LABELS: Record<PostState, string> = {
  candidate: 'Candidate',
  booked: 'Booked',
  drafting: 'Drafting',
  needs_fix: 'Needs fix',
  draft_ready: 'Draft ready',
  scheduled: 'Scheduled',
  released: 'Released',
  posted: 'Posted',
}

export const POST_FLAG_LABELS: Record<PostFlag, string> = {
  no_date: 'No date',
  no_channel: 'No channel',
  stale: 'Stale',
  holiday: 'Holiday',
  operator: 'Operator',
}

export type PostingWeekPost = {
  calendar_id: string
  title: string
  primary_channel?: string | null
  source_type?: string | null
  calendar_status?: string | null
  state?: PostState
  flags?: PostFlag[]
  stages: Record<string, boolean>
  stage?: string
  inbox_item_id?: string | null
  asset_id?: string | null
  image_url?: string | null
  next_action?: string
  needs_fix_reason?: string
}

export type PostingWeekDay = {
  date: string
  weekday: string
  is_today?: boolean
  is_past?: boolean
  posts: PostingWeekPost[]
  holidays?: { title?: string }[]
}

const GOES_OUT_MONTHS_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const

const POSTING_CHANNEL_LABELS: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  gbp: 'GBP',
}

export type PostingWeekPayload = {
  ok: boolean
  brand?: string
  timezone?: string
  start?: string
  days?: number
  past_days?: number
  days_list?: PostingWeekDay[]
  undated?: PostingWeekPost[]
  undated_total?: number
  orphan_drafts?: number
  counts?: {
    moments?: number
    drafts?: number
    queued?: number
    released?: number
    posted?: number
    candidates?: number
    needs_fix?: number
    stale?: number
  }
  error?: string
}

export function formatPostingDayHeader(day: PostingWeekDay): string {
  const d = day.date.slice(8, 10)
  const mon = day.date.slice(5, 7)
  return `${day.weekday} ${d}/${mon}`
}

export function primaryStageFromStages(stages: Record<string, boolean>): PostingStageKey {
  let last: PostingStageKey = 'booked'
  for (const key of POSTING_STAGE_ORDER) {
    if (stages[key]) last = key
  }
  return last
}

/** First stage in pipeline order that is not marked complete. */
export function firstIncompleteStageFromStages(
  stages: Record<string, boolean>,
): PostingStageKey | null {
  for (const key of POSTING_STAGE_ORDER) {
    if (!stages[key]) return key
  }
  return null
}

const NEXT_ACTION_BY_INCOMPLETE: Record<PostingStageKey, string> = {
  booked: 'Waiting on caption',
  caption: 'Waiting on caption',
  image: 'Waiting on image',
  in_review: 'Ready to review',
  approved: 'Needs your look',
  queued: 'Approved',
  released: 'Waiting to go out',
  posted: 'Posted',
}

/** Human next-step copy from lodge row stage flags. */
export function nextActionFromStages(stages: Record<string, boolean>): string {
  const incomplete = firstIncompleteStageFromStages(stages)
  if (!incomplete) return 'Posted'
  return NEXT_ACTION_BY_INCOMPLETE[incomplete]
}

export function postingChannelLabel(raw?: string | null): string | null {
  const key = String(raw ?? '')
    .trim()
    .toLowerCase()
  if (!key) return null
  return POSTING_CHANNEL_LABELS[key] ?? null
}

/** Card line: "Goes out Thu 24 Sep" (weekday hint from API when present). */
export function formatGoesOut(dayIso: string, weekdayHint?: string | null): string {
  const trimmed = String(dayIso ?? '').trim()
  const ymd = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!ymd) return 'Goes out'
  const monthIndex = Number(ymd[2]) - 1
  const day = Number(ymd[3])
  const month =
    monthIndex >= 0 && monthIndex < 12 ? GOES_OUT_MONTHS_SHORT[monthIndex] : ymd[2]
  const wd = String(weekdayHint ?? '').trim()
  if (wd) return `Goes out ${wd} ${day} ${month}`
  return `Goes out ${day} ${month}`
}

export function postingWeekThumbUrl(raw?: string | null): string | null {
  const url = String(raw ?? '').trim()
  return url ? url : null
}

export function emptyWeekBuckets(startIso: string, days: number): string[] {
  const out: string[] = []
  const start = new Date(`${startIso}T12:00:00`)
  for (let i = 0; i < days; i += 1) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    out.push(d.toISOString().slice(0, 10))
  }
  return out
}

export function postStateLabel(state?: PostState | string | null): string {
  const key = String(state ?? '') as PostState
  return POST_STATE_LABELS[key] ?? String(state ?? '—')
}

export function postFlagLabel(flag: PostFlag | string): string {
  const key = flag as PostFlag
  return POST_FLAG_LABELS[key] ?? flag
}

export function postStateTone(state?: PostState | string | null): 'mute' | 'warn' | 'ok' | 'bad' {
  switch (state) {
    case 'needs_fix':
      return 'bad'
    case 'candidate':
    case 'drafting':
      return 'warn'
    case 'posted':
    case 'released':
    case 'scheduled':
    case 'draft_ready':
      return 'ok'
    default:
      return 'mute'
  }
}

export function linkForPostState(post: PostingWeekPost): string | null {
  switch (post.state) {
    case 'draft_ready':
      if (post.inbox_item_id) return `/review/${encodeURIComponent(post.inbox_item_id)}`
      return '/review'
    case 'scheduled':
      return '/shelf'
    case 'candidate':
      return '/inbox'
    default:
      if (post.inbox_item_id) return `/review/${encodeURIComponent(post.inbox_item_id)}`
      return null
  }
}
