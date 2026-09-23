export type PostingStageKey =
  | 'booked'
  | 'caption'
  | 'image'
  | 'in_review'
  | 'approved'
  | 'queued'

export const POSTING_STAGE_ORDER: PostingStageKey[] = [
  'booked',
  'caption',
  'image',
  'in_review',
  'approved',
  'queued',
]

export const POSTING_STAGE_LABELS: Record<PostingStageKey, string> = {
  booked: 'Booked',
  caption: 'Caption',
  image: 'Image',
  in_review: 'In review',
  approved: 'Approved',
  queued: 'Queued',
}

export type PostingWeekPost = {
  calendar_id: string
  title: string
  primary_channel?: string | null
  stages: Record<string, boolean>
  stage?: string
  inbox_item_id?: string | null
  asset_id?: string | null
  image_url?: string | null
}

export type PostingWeekDay = {
  date: string
  weekday: string
  is_today?: boolean
  posts: PostingWeekPost[]
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
  days_list?: PostingWeekDay[]
  orphan_drafts?: number
  counts?: { moments?: number; drafts?: number; queued?: number }
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
}

/** Human next-step copy from lodge row stage flags. */
export function nextActionFromStages(stages: Record<string, boolean>): string {
  const incomplete = firstIncompleteStageFromStages(stages)
  if (!incomplete) return 'In the sandbox'
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
