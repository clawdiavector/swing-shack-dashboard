export type TodayCounts = {
  review: number
  draft: number
  approved: number
  published: number
  scheduled: number
  total: number
}

export type TodayCard = {
  id: string
  label: string
  kind: string
  title: string
  campaignId?: string
  updatedAt?: string
  createdAt?: string
  stamp?: string
  stampKind?: 'updated' | 'created' | 'scheduled' | 'as_of'
  why?: string
}

export type BriefAction = {
  event_key?: string
  name?: string
  action?: string
  brief_id?: string
  brief_status?: string
  gate?: string
}

export type TodayPanel = {
  ok: boolean
  ts?: string
  summary?: string
  cards?: TodayCard[]
  active_brand_id?: string
  active_brand_label?: string
  counts?: TodayCounts
  brief_actions?: { brand_id?: string; count?: number; actions?: BriefAction[] }
  error?: string
}

export type InboxItem = {
  id: string
  type?: string
  status?: string
  brand_id?: string
  title?: string
  summary?: string
  created_at?: string
  sla_state?: string
  actions?: string[]
  meta?: {
    campaign_id?: string
    asset_id?: string
    platform?: string
    approval_status?: string
  }
}

export type InboxPayload = {
  ok: boolean
  items?: InboxItem[]
  counts?: { pending?: number; stale?: number; approved_today?: number }
  error?: string
}

export type LayerEntry = {
  label?: string
  verdict?: string
  pending?: number
  stale?: number
  href?: string
  inbox_href?: string
  winners?: number
  never?: number
  reporting?: number
  agents?: number
  queue_approved_ready?: number
  rotten?: number
  recipes?: number
  late?: number
  stuck?: number
  failed?: number
  samples?: number
}

export type LayersPayload = {
  ok?: boolean
  layers?: Record<string, LayerEntry>
  error?: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  if (!res.ok) {
    throw new Error(`${path} ${res.status}`)
  }
  return res.json() as Promise<T>
}

export function fetchToday(brand?: string) {
  const q = brand ? `?brand=${encodeURIComponent(brand)}` : ''
  return getJson<TodayPanel>(`/api/today/panel${q}`)
}

export type CalendarItem = {
  calendar_id?: string
  title?: string
  type?: string
  status?: string
  event_date?: string
  campaign_start?: string
  campaign_end?: string
}

export type CalendarView = {
  ok?: boolean
  items?: CalendarItem[]
  calendar_count?: number
  error?: string
}

export async function fetchCalendarMonth(brand: string, start: string, end: string) {
  const q = new URLSearchParams({ start, end, include_watchlist: 'true' })
  const res = await fetch(`/api/calendar/calendar/${encodeURIComponent(brand)}?${q}`, {
    credentials: 'same-origin',
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  if (!res.ok) return { ok: false, items: [] } as CalendarView
  return res.json() as Promise<CalendarView>
}

export function fetchInbox(status = 'pending') {
  return getJson<InboxPayload>(`/api/inbox/unified?status=${encodeURIComponent(status)}`)
}

export function matchInboxItem(item: InboxItem, id: string) {
  if (!id) return false
  if (item.id === id) return true
  if (item.meta?.asset_id === id) return true
  return item.id.endsWith(`:${id}`)
}

export async function fetchInboxItem(id: string) {
  const pending = await fetchInbox('pending')
  const fromPending = (pending.items || []).find((item) => matchInboxItem(item, id))
  if (fromPending) return fromPending
  const all = await fetchInbox('all')
  return (all.items || []).find((item) => matchInboxItem(item, id)) || null
}

export function fetchLayers() {
  return getJson<LayersPayload>('/api/ops/layers')
}

export type LearnHeadline = {
  verdict?: string
  winners?: number
  recipes?: number
  samples?: number
  proposal_gate?: string
  last_recipe_at?: string | null
  ready?: boolean
}

export type LearnMover = {
  post_id?: string
  hook_id?: string
  score?: number
  rank?: number
}

export type LearnSummary = {
  ok?: boolean
  generated_at?: string
  headline?: LearnHeadline
  post_outcomes?: { posts_total?: number; top_movers?: LearnMover[] }
}

export function fetchLearn() {
  return getJson<LearnSummary>('/api/ops/learn/summary')
}

export type InsightPost = {
  id?: string
  caption_excerpt?: string
  engagementRate?: number
  verdict?: string
  plain_english?: string
  like_count?: number
  timestamp?: string
}

export type InsightsPosts = {
  ok?: boolean
  posts?: InsightPost[]
  _meta?: { average_engagement?: number; total_scanned?: number; fetched_at?: string; reason?: string }
}

export function fetchTopPosts(brand?: string) {
  const q = new URLSearchParams({ limit: '3' })
  if (brand) q.set('brand_id', brand)
  return getJson<InsightsPosts>(`/api/insights/top-instagram-posts?${q}`)
}

export type BrandRecord = {
  id?: string
  display_name?: string
  name?: string
  label?: string
  short_label?: string
  icon?: string
  active?: boolean
  order?: number
}

export function fetchBrands() {
  return getJson<{
    active_brand_id?: string
    default_brand_id?: string
    brands?: Record<string, BrandRecord>
  }>('/api/brands')
}

export async function selectBrand(brandId: string) {
  const res = await fetch(`/api/brands/${encodeURIComponent(brandId)}/select`, {
    method: 'POST',
    credentials: 'same-origin',
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  if (!res.ok) throw new Error(`select brand ${res.status}`)
  return res.json() as Promise<{ ok?: boolean; brand_id?: string }>
}

export async function inboxAction(id: string, action: 'approve' | 'reject', reason = '') {
  const res = await fetch(`/api/inbox/unified/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ editor: 'operator', reason }),
  })
  return res.json() as Promise<{ ok?: boolean; error?: string }>
}
