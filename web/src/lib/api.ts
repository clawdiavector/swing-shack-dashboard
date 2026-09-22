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

export type JobBrandEntry = {
  brand?: string
  verdict?: string
  applies?: boolean
  last_success_at?: string | null
  last_success_age_h?: number | null
  last_run_at?: string | null
  last_status?: string | null
  last_error?: string | null
  skipped_reason?: string | null
}

export type JobEntry = {
  name?: string
  verdict?: string
  criticality?: string
  brand_mode?: string
  last_success_at?: string | null
  last_success_age_h?: number | null
  last_run_at?: string | null
  last_started_at?: string | null
  last_triggered_by?: string | null
  last_status?: string | null
  last_error?: string | null
  last_duration_s?: number | null
  last_run_id?: string | null
  last_error_class?: string | null
  best_effort?: boolean
  enabled?: boolean
  every_seconds?: number | null
  timeout_seconds?: number | null
  retries?: number | null
  schedule?: string | null
  info?: string | null
  brands?: JobBrandEntry[]
}

export type JobsStatus = {
  jobs?: JobEntry[]
}

export function fetchJobsStatus() {
  return getJson<JobsStatus>('/api/jobs/status')
}

export type AgentRow = {
  id?: string
  profile?: string
  kind?: string
  layer?: string
  schedule?: string | null
  enabled?: boolean
  last_heartbeat_at?: string | null
  last_status?: string | null
  last_action?: string | null
  last_writes?: string[]
  skill?: string | null
}

export type AgentsPayload = {
  schema?: string
  generated_at?: string
  agents?: AgentRow[]
}

export function fetchAgents() {
  return getJson<AgentsPayload>('/api/ops/agents')
}

export type QueueRow = {
  id?: string
  layer?: string
  agent?: string
  brand?: string
  action?: string
  payload_ref?: string | null
  status?: string
}

export type QueuePayload = {
  ok?: boolean
  schema?: string
  generated_at?: string
  rows?: QueueRow[]
  counts?: { pending?: number; done?: number; total?: number }
}

export function fetchAgentQueue(opts?: {
  agent?: string
  brand?: string
  status?: string
  limit?: number
}) {
  const q = new URLSearchParams()
  if (opts?.agent) q.set('agent', opts.agent)
  if (opts?.brand) q.set('brand', opts.brand)
  if (opts?.status) q.set('status', opts.status)
  if (opts?.limit != null) q.set('limit', String(opts.limit))
  const suffix = q.toString() ? `?${q}` : ''
  return getJson<QueuePayload>(`/api/ops/agent-queue${suffix}`)
}

export type AccountConnect = {
  type?: string
  url?: string
  label?: string
  method?: string
}

export type AccountSetup = {
  auth_type?: string
  env_vars?: string[]
  steps?: string[]
}

export type AccountItem = {
  id?: string
  icon?: string
  name?: string
  category?: string
  state?: string
  purpose?: string
  last_used_at?: string | null
  connect?: AccountConnect
  setup?: AccountSetup
  details?: Record<string, unknown>
  na_reason?: string
  error?: string
}

export type AccountCategory = {
  id?: string
  label?: string
  items?: AccountItem[]
}

export type AccountsStatus = {
  ok?: boolean
  brand?: string
  last_check?: string | null
  summary?: Record<string, number>
  categories?: AccountCategory[]
  error?: string
}

export function fetchAccounts(brand: string) {
  const q = new URLSearchParams({ brand })
  return getJson<AccountsStatus>(`/api/connected-accounts/status?${q}`)
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
