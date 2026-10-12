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
  | 'partly_posted'
  | 'send_failed'

export type DeliveryStatus =
  | 'not_picked'
  | 'awaiting_approval'
  | 'queued'
  | 'sending'
  | 'posted'
  | 'failed'
  | 'skipped'
  | 'coming_soon'

export type PostDelivery = {
  channel: string
  status: DeliveryStatus | string
  idempotency_key?: string
  would_publish_at?: string | null
  dispatched_at?: string | null
  external_id?: string | null
  attempts?: number
  last_error?: string | null
}

export type DeliverySummary = {
  picked?: number
  posted?: number
  failed?: number
  queued?: number
}

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
  partly_posted: 'Partly posted',
  send_failed: 'Send failed',
}

export const POST_FLAG_LABELS: Record<PostFlag, string> = {
  no_date: 'No date',
  no_channel: 'No channel',
  stale: 'Stale',
  holiday: 'Holiday',
  operator: 'Operator',
}

export type RenderMode = 'template' | 'oneshot'

export const RENDER_MODE_LABELS: Record<RenderMode, string> = {
  template: 'Template',
  oneshot: 'One-shot',
}

export type PostingWeekPost = {
  calendar_id: string
  brand_id?: string
  title: string
  angle?: string | null
  render_mode?: RenderMode
  post_type?: string | null
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
  template_id?: string
  template_name?: string
  template_label?: string
  template_reference_urls?: string[]
  sandbox?: { would_publish_at?: string | null; platform?: string | null }[]
  post_id?: string | null
  channels_available?: string[]
  channels_coming?: string[]
  channels_picked?: string[]
  channels_locked?: boolean
  deliveries?: PostDelivery[]
  delivery_summary?: DeliverySummary
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
  gbp: 'Google Business',
  youtube: 'YouTube',
  tiktok: 'TikTok',
}

const POSTING_CHANNEL_ABBREV: Record<string, string> = {
  facebook: 'FB',
  instagram: 'IG',
  gbp: 'GBP',
  youtube: 'YouTube',
  tiktok: 'TikTok',
}

export type ShelfDateGroup = {
  date: string
  posts: PostingWeekPost[]
}

export type ShelfPayload = {
  ok?: boolean
  brand?: string
  timezone?: string
  today?: string
  date_groups?: ShelfDateGroup[]
  undated?: PostingWeekPost[]
  counts?: {
    scheduled?: number
    released?: number
    undated?: number
    releasable_today?: number
    released_today?: number
    attention?: number
  }
  error?: string
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
  return POSTING_CHANNEL_LABELS[key] ?? key.replace(/_/g, ' ')
}

export function postingChannelAbbrev(raw?: string | null): string {
  const key = String(raw ?? '')
    .trim()
    .toLowerCase()
  if (!key) return ''
  return POSTING_CHANNEL_ABBREV[key] ?? postingChannelLabel(key) ?? key
}

/** "IG + FB" for Review list lines. */
export function channelsPickedSummary(channels?: string[] | null): string {
  const list = (channels ?? []).map((c) => postingChannelAbbrev(c)).filter(Boolean)
  return list.join(' + ')
}

export function defaultChannelsForBrand(_brandId?: string): string[] {
  return ['instagram', 'facebook']
}

export function deliveryChipLabel(status?: string | null): string {
  const key = String(status ?? '').toLowerCase()
  switch (key) {
    case 'not_picked':
      return 'Not picked'
    case 'awaiting_approval':
      return 'Awaiting approval'
    case 'queued':
      return 'Queued'
    case 'sending':
      return 'Sending'
    case 'posted':
      return 'Posted'
    case 'failed':
      return 'Failed'
    case 'skipped':
      return 'Skipped'
    case 'coming_soon':
      return 'Coming later'
    default:
      return key ? key.replace(/_/g, ' ') : '—'
  }
}

export function deliveryChipTone(status?: string | null): 'mute' | 'warn' | 'ok' | 'bad' | 'gold' {
  const key = String(status ?? '').toLowerCase()
  switch (key) {
    case 'posted':
      return 'ok'
    case 'failed':
      return 'bad'
    case 'queued':
    case 'sending':
      return 'gold'
    case 'awaiting_approval':
      return 'warn'
    default:
      return 'mute'
  }
}

/** One status line from post state + deliveries (when API sends them). */
export function postFactLine(
  post: Pick<PostingWeekPost, 'state' | 'next_action' | 'deliveries' | 'delivery_summary'>,
  dayDate: string,
  weekday: string,
  goesOutAt?: string | null,
): string {
  const sastClock = formatSastClock(goesOutAt)
  const datePart = dayDate ? formatGoesOut(dayDate, weekday) : null
  const summary = post.delivery_summary
  if (post.state === 'partly_posted' && summary) {
    const failed = post.deliveries?.find((d) => d.status === 'failed')
    const err = failed?.last_error ? `: ${String(failed.last_error).slice(0, 60)}` : ''
    return `Posted to ${summary.posted ?? 0} of ${summary.picked ?? 0}${err}`
  }
  if (post.state === 'send_failed') {
    const failed = post.deliveries?.find((d) => d.status === 'failed')
    const ch = failed ? postingChannelLabel(failed.channel) : 'Channel'
    const err = failed?.last_error ? `: ${String(failed.last_error).slice(0, 80)}` : ''
    return `${ch} failed${err}`
  }
  const nextAction = post.next_action || '—'
  return [datePart, sastClock, nextAction].filter(Boolean).join(' · ')
}

/** 13:00 SAST from a real UTC instant. Does not use the browser timezone. */
export function formatSastClock(iso?: string | null): string | null {
  const raw = String(iso ?? '').trim()
  if (!raw) return null
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return null
  const clock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Africa/Johannesburg',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(d)
  return `${clock} SAST`
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
    case 'send_failed':
      return 'bad'
    case 'partly_posted':
      return 'warn'
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

export function isAttentionPostState(state?: PostState | string | null): boolean {
  return state === 'partly_posted' || state === 'send_failed'
}

export function renderModeOf(post: PostingWeekPost): RenderMode {
  const raw = String(post.render_mode ?? '')
    .trim()
    .toLowerCase()
  if (raw === 'oneshot') return 'oneshot'
  return 'template'
}

export function renderModeEditable(state?: PostState | string | null): boolean {
  const s = String(state ?? '')
  return (
    s !== 'scheduled' &&
    s !== 'released' &&
    s !== 'posted' &&
    s !== 'partly_posted' &&
    s !== 'send_failed'
  )
}

export const ONESHOT_POST_TYPES = new Set([
  'fitting_headline',
  'service_hero',
  'coaching_promo',
  'zine_collage',
  'humour_card',
])

export const TEMPLATE_ONLY_POST_TYPES = new Set([
  'price_list',
  'price_package',
  'pricing',
  'package',
  'packages',
  'rate_card',
  'package_list',
  'discount_code',
  'promo_code',
  'offer',
  'sale_offer',
  'location',
  'shop_corner',
  'service_square',
  'service_end',
  'brand_statement',
])

/** Mirrors backend oneshot_blocked — template-only post types cannot flip to one-shot. */
export function oneshotEligible(postType?: string | null): boolean {
  return !TEMPLATE_ONLY_POST_TYPES.has(String(postType ?? '').trim().toLowerCase())
}

const SAST = 'Africa/Johannesburg'

/** Today as YYYY-MM-DD in SAST (not the browser local calendar). */
export function sastTodayIso(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: SAST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const y = parts.find((p) => p.type === 'year')?.value ?? '1970'
  const m = parts.find((p) => p.type === 'month')?.value ?? '01'
  const d = parts.find((p) => p.type === 'day')?.value ?? '01'
  return `${y}-${m}-${d}`
}

function addDaysIso(iso: string, delta: number): string {
  const [y, mo, d] = iso.split('-').map(Number)
  const utc = new Date(Date.UTC(y, mo - 1, d + delta, 12))
  return utc.toISOString().slice(0, 10)
}

/** Resolve day desk anchor from URL params; malformed date → SAST today. */
export function dayAnchorFromParams(
  tab: string | null,
  dateParam: string | null,
  now: Date = new Date(),
): { tab: 'week' | 'day'; dateIso: string } {
  const mode = tab === 'day' ? 'day' : 'week'
  if (mode === 'week') {
    return { tab: 'week', dateIso: sastTodayIso(now) }
  }
  const raw = String(dateParam ?? '').trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const parsed = new Date(`${raw}T12:00:00`)
    if (!Number.isNaN(parsed.getTime())) {
      return { tab: 'day', dateIso: raw }
    }
  }
  return { tab: 'day', dateIso: sastTodayIso(now) }
}

export function sastTomorrowIso(now: Date = new Date()): string {
  return addDaysIso(sastTodayIso(now), 1)
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
