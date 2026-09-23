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
