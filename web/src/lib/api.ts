import type { PostingWeekPayload, ShelfPayload } from './postingWeek'

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
  creative_allowed?: boolean
  brief_revision?: number
  gate_confidence?: number
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
    primary_channel?: string
    event_date?: string
    goes_out_at?: string
    approval_status?: string
    caption?: string
    image_path?: string
    image_url?: string
    state?: string
    flags?: string[]
    source_type?: string
    created_by?: string
    calendar_id?: string
  }
}

export type InboxPayload = {
  ok: boolean
  items?: InboxItem[]
  counts?: { pending?: number; stale?: number; approved_today?: number; approved?: number }
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

export async function getJson<T>(path: string): Promise<T> {
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

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
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
  brand_id?: string
  title?: string
  type?: string
  status?: string
  event_date?: string
  event_end?: string
  campaign_start?: string
  campaign_end?: string
  pillars?: string[]
  colour?: string
  relevance_score?: number
  relevance_reason?: string
  commercial_relevance?: number | string
  audience_relevance?: number | string
  brand_relevance?: number | string
  timeliness?: number | string
  confidence?: number | string
  lead_time_days?: number
  lead_time_schedule?: { planning_start?: string } & Record<string, unknown>
  planning_start?: string
  source_urls?: string[]
  source_type?: string
  source_domain?: string
  source_title?: string
  source_class?: string
  suggested_angles?: string[]
  verification_status?: string
  trusted_for_planning?: boolean
  event_lifecycle?: string
  opportunity_mode?: string
  date_confidence?: string
  retrieved_at?: string
  created_by?: string
}

export type CalendarView = {
  ok?: boolean
  items?: CalendarItem[]
  calendar_count?: number
  error?: string
  status?: number
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
  if (!res.ok) {
    let error = ''
    try {
      const j = (await res.json()) as { error?: string }
      error = j.error || ''
    } catch {
      error = ''
    }
    return { ok: false, items: [], error, status: res.status } as CalendarView
  }
  return res.json() as Promise<CalendarView>
}

export type IntelCalendarSlot = {
  source?: string
  assetId?: string
  campaignId?: string
  campaignName?: string
  name?: string
  caption?: string
  approvalStatus?: string
  publishStatus?: string
  platform?: string
  brand?: string
  pillar?: string
  color?: string
  scheduledFor?: string
}

export type IntelCalendarDay = {
  date?: string
  weekday?: string
  count?: number
  slots?: IntelCalendarSlot[]
}

export type IntelCalendarPayload = {
  ok?: boolean
  ts?: string
  today?: string
  totalScheduled?: number
  days?: IntelCalendarDay[]
  error?: string
}

export function fetchIntelCalendar(brand: string, startIso: string, days: number) {
  const q = new URLSearchParams({
    brand: brand,
    start: startIso,
    days: String(days),
  })
  return getJson<IntelCalendarPayload>(`/api/intel/calendar?${q}`)
}

export type OpportunitiesPayload = {
  ok?: boolean
  ts?: string
  ideas?: unknown[]
  post_today?: unknown[]
  this_week?: unknown[]
  reels?: unknown[]
  missed?: unknown[]
  upsells?: unknown[]
  bundles?: unknown[]
  landing_fixes?: unknown[]
  lead_capture_fixes?: unknown[]
  funnel_leaks?: unknown[]
  error?: string
}

export function fetchOpportunities(brand: string) {
  const q = new URLSearchParams({ brand })
  return getJson<OpportunitiesPayload>(`/api/intel/opportunities?${q}`)
}

export type CalendarCandidateBody = {
  brand_id: string
  type: string
  title: string
  event_date: string
  source_type?: string
  status?: string
  pillars?: string[]
  suggested_angles?: string[]
  campaign_ids?: string[]
  product_brand?: string
}

export type CalendarCandidateRecord = {
  ok?: boolean
  record?: { calendar_id?: string; status?: string; created_at?: string }
  error?: string
}

export function addCalendarCandidate(body: CalendarCandidateBody) {
  return postJson<CalendarCandidateRecord>('/api/calendar/candidates', body)
}

export type CalendarTransitionBody = {
  brand_id: string
  calendar_id: string
  new_status: string
  reason?: string
}

export function transitionCalendarRecord(body: CalendarTransitionBody) {
  return postJson<{ ok?: boolean; error?: string }>('/api/calendar/transition', body)
}

export function fetchCalendarCandidates(brand: string, status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return getJson<{ ok?: boolean; records?: unknown[]; count?: number }>(
    `/api/calendar/candidates/${encodeURIComponent(brand)}${q}`,
  )
}

export function fetchPlanningBigIdea(brand: string) {
  return getJson<Record<string, unknown>>(`/api/planning/${encodeURIComponent(brand)}/big-idea`)
}

export function fetchPlanningMonth(brand: string, month: string) {
  const q = new URLSearchParams({ month })
  return getJson<Record<string, unknown>>(
    `/api/planning/${encodeURIComponent(brand)}/month?${q}`,
  )
}

export function fetchPlanningRightNow(brand: string) {
  return getJson<Record<string, unknown>>(`/api/planning/${encodeURIComponent(brand)}/right-now`)
}

export function fetchPlanningTimeline(brand: string, year: string) {
  const q = new URLSearchParams({ year })
  return getJson<Record<string, unknown>>(
    `/api/planning/${encodeURIComponent(brand)}/timeline?${q}`,
  )
}

export function fetchPlanningEvent(brand: string, eventId: string) {
  return getJson<Record<string, unknown>>(
    `/api/planning/${encodeURIComponent(brand)}/event/${encodeURIComponent(eventId)}`,
  )
}

export function fetchImportantDates(year: string) {
  const q = new URLSearchParams({ year })
  return getJson<Record<string, unknown>>(`/api/important-dates?${q}`)
}

export function generateIdeas(brand: string, n = 6, platform = 'instagram') {
  const q = new URLSearchParams({ brand })
  return postJson<Record<string, unknown>>(`/api/intel/generate_ideas?${q}`, { n, platform })
}

export type ScheduleResult = {
  ok?: boolean
  assetId?: string
  scheduledFor?: string
  error?: string
}

export function rescheduleAsset(
  assetId: string,
  body: { campaignId?: string; scheduledFor: string; platform?: string; updatedBy?: string },
) {
  return postJson<ScheduleResult>(`/api/schedule/${encodeURIComponent(assetId)}`, body)
}

export function duplicateScheduledAsset(assetId: string, body: Record<string, unknown>) {
  return postJson<ScheduleResult>(`/api/schedule/${encodeURIComponent(assetId)}/duplicate`, body)
}

export async function unscheduleAsset(assetId: string) {
  const res = await fetch(`/api/schedule/${encodeURIComponent(assetId)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  return res.json() as Promise<ScheduleResult>
}

export function fetchInbox(status = 'pending', brand?: string, type?: string) {
  const q = new URLSearchParams({ status })
  if (brand) q.set('brand', brand)
  if (type) q.set('type', type)
  return getJson<InboxPayload>(`/api/inbox/unified?${q}`)
}

export function fetchPostingWeek(
  brand?: string,
  opts?: { past?: number; days?: number; start?: string; includeCandidates?: boolean },
) {
  const q = new URLSearchParams()
  if (brand) q.set('brand', brand)
  if (opts?.past != null) q.set('past', String(opts.past))
  if (opts?.days != null) q.set('days', String(opts.days))
  if (opts?.start) q.set('start', opts.start)
  if (opts?.includeCandidates === false) q.set('include_candidates', '0')
  return getJson<PostingWeekPayload>(`/api/inbox/week?${q}`)
}

export function fetchShelf(brand?: string) {
  const q = new URLSearchParams()
  if (brand) q.set('brand', brand)
  return getJson<ShelfPayload>(`/api/inbox/shelf?${q}`)
}

export function releaseMoment(brandId: string, calendarId: string, editor = 'christelle') {
  return postJsonWithStatus<{
    ok?: boolean
    error?: string
    code?: string
    state?: string
    released?: string[]
    dispatched?: string[]
    would_publish_at?: string
  }>('/api/publish/release', { brand_id: brandId, calendar_id: calendarId, editor })
}

export function matchInboxItem(item: InboxItem, id: string) {
  if (!id) return false
  if (item.id === id) return true
  if (item.meta?.asset_id === id) return true
  return item.id.endsWith(`:${id}`)
}

export async function fetchInboxItem(id: string, brand?: string) {
  const pending = await fetchInbox('pending', brand)
  const fromPending = (pending.items || []).find((item) => matchInboxItem(item, id))
  if (fromPending) return fromPending
  const all = await fetchInbox('all', brand)
  return (all.items || []).find((item) => matchInboxItem(item, id)) || null
}

export function fetchLayers(brand?: string) {
  const q =
    brand && brand.trim()
      ? `?brand=${encodeURIComponent(brand.trim())}`
      : ''
  return getJson<LayersPayload>(`/api/ops/layers${q}`)
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

/** `/api/jobs/status` — `campaign-os/_lib/jobs/descriptions.py`. */
export type JobInfoObject = {
  title?: string
  summary?: string
  detail?: string
}

/** `/api/jobs/status` — `campaign-os/_lib/jobs/schedules.py`. */
export type JobScheduleObject = {
  cadence?: string
  cron_sast?: string[] | unknown
  scheduler?: string
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
  schedule?: string | JobScheduleObject | null
  info?: string | JobInfoObject | null
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
  permalink?: string
  thumbnail_url?: string
  media_url?: string
  media_type?: string
  oembed_thumbnail?: string
}

export type InsightsPosts = {
  ok?: boolean
  posts?: InsightPost[]
  _meta?: { average_engagement?: number; total_scanned?: number; fetched_at?: string; reason?: string }
}

export function fetchTopPosts(brand?: string, limit = 3) {
  const q = new URLSearchParams({ limit: String(limit) })
  if (brand) q.set('brand_id', brand)
  return getJson<InsightsPosts>(`/api/insights/top-instagram-posts?${q}`)
}

export type WeeklyReportJson = {
  brand_id?: string
  data_source_brand_id?: string
  brand_meta?: Record<string, unknown>
  metrics?: Record<string, unknown>
}

export type WeekOnWeekCell = {
  current?: number
  previous?: number
  delta?: number
  pct_change?: number
}

/** Rule-based weekly intel narrative (`campaign-os/_lib/intelligence.py`). */
export type IntelWeeklyInterpretationClaim = {
  claim?: string
  evidence?: string
  source?: string
  category?: string
  severity?: string
}

export type IntelWeeklyInterpretation = {
  headline_take?: string
  whats_working?: IntelWeeklyInterpretationClaim[] | unknown[]
  whats_not?: IntelWeeklyInterpretationClaim[] | unknown[]
  look_at?: IntelWeeklyInterpretationClaim[] | unknown[]
  sources_used?: string[] | unknown
}

export type IntelWeeklyReport = {
  ok?: boolean
  ts?: string
  week_start?: string
  week_end?: string
  window_label?: string
  window_note?: string
  brand?: string
  headline?: string
  headline_kpis?: {
    published?: number
    failed?: number
    win_rate_pct?: number
    agent_runs?: number
    agent_pass_rate_pct?: number
  }
  platforms?: unknown
  by_day?: unknown
  top_hooks?: unknown[]
  top_ctas?: unknown[]
  seo_movers?: unknown[]
  failures?: { item_id?: string; platform?: string; reason?: string; ts?: string }[]
  agent_breakdown?: Record<
    string,
    { total?: number; passed?: number; failed?: number; partial?: number; pass_rate_pct?: number }
  >
  week_on_week?: Record<string, WeekOnWeekCell>
  ga4?: unknown
  youtube?: unknown
  reddit?: unknown
  ig_business?: unknown
  seo_health?: unknown
  interpretation?: string | IntelWeeklyInterpretation
  visual_insights?: unknown
  ig_topic_clusters?: unknown
  export_path?: string
}

export function fetchWeeklyReportJson(brand: string) {
  const q = new URLSearchParams({ brand, format: 'json' })
  return getJson<WeeklyReportJson>(`/api/weekly-report?${q}`)
}

export function fetchIntelWeeklyReport() {
  return getJson<IntelWeeklyReport>('/api/intel/weekly_report')
}

export async function snapshotWeeklyReport(brand: string) {
  const q = new URLSearchParams({ brand })
  const res = await fetch(`/api/weekly-report/snapshot?${q}`, {
    method: 'POST',
    credentials: 'same-origin',
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  if (!res.ok) throw new Error(`/api/weekly-report/snapshot ${res.status}`)
  return res.json() as Promise<{ brand_id?: string; path?: string; iso_week?: unknown }>
}

export type WeeklyShareResponse = {
  ok?: boolean
  share_url?: string
  expires_at?: string
  ttl_seconds?: number
  error?: string
}

export function shareWeeklyReport(ttlSeconds?: number) {
  const body = ttlSeconds != null ? { ttl_seconds: ttlSeconds } : {}
  return postJson<WeeklyShareResponse>('/api/intel/weekly_report/share', body)
}

export type LearningRow = { title?: string; kind?: string; why?: string }

export type IntelLearning = {
  ok?: boolean
  ts?: string
  what_worked?: LearningRow[]
  what_failed?: LearningRow[]
  recommendation_outcomes?: unknown[]
  best_recommendation?: unknown
  trend_delta?: unknown
  cta_rankings?: unknown[]
  failure_patterns?: unknown[]
  confidence_bands?: Record<string, unknown>
  data_as_of?: Record<string, string | null | undefined>
}

export function fetchIntelLearning() {
  return getJson<IntelLearning>('/api/intel/learning')
}

export type ContentTrafficMatch = Record<string, unknown>

export type ContentTrafficCorrelation = {
  ok?: boolean
  matches?: ContentTrafficMatch[]
  unmatched_spikes?: ContentTrafficMatch[]
  _meta?: { fetched_at?: string; reason?: string }
}

export function fetchContentTrafficCorrelation(brand: string, days = 30) {
  const q = new URLSearchParams({ days: String(days), brand_id: brand })
  return getJson<ContentTrafficCorrelation>(`/api/insights/content-traffic-correlation?${q}`)
}

export type AdCorrelation = {
  ok?: boolean
  configured?: boolean
  google_ads?: Record<string, unknown>
  meta_ads?: Record<string, unknown>
  combined_summary?: string
  error?: string
}

export function fetchAdCorrelation() {
  return getJson<AdCorrelation>('/api/insights/ad-correlation')
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

export async function inboxAction(
  id: string,
  action: 'approve' | 'reject',
  reason = '',
  mode?: 'lodge' | 'book',
) {
  const body: Record<string, string> = { editor: 'operator', reason }
  if (action === 'approve' && mode) body.mode = mode
  const res = await fetch(`/api/inbox/unified/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json() as Promise<{ ok?: boolean; error?: string; code?: string }>
}

export async function inboxEdit(id: string, fields: Record<string, string>, editor = 'christelle') {
  const res = await fetch(`/api/inbox/unified/${encodeURIComponent(id)}/edit`, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ editor, ...fields }),
  })
  const data = (await res.json()) as {
    ok?: boolean
    error?: string
    code?: string
    changed?: string[]
    item?: InboxItem
  }
  if (!res.ok && !data.error) {
    data.error = `edit ${res.status}`
  }
  return data
}

export type AssetAiDraft = {
  ok?: boolean
  assetId?: string
  campaignId?: string
  caption?: string
  source?: string
  ts?: string
  error?: string
}

export function fetchAssetAiDraft(assetId: string, campaignId?: string) {
  const q = new URLSearchParams()
  if (campaignId) q.set('campaignId', campaignId)
  const suffix = q.toString() ? `?${q}` : ''
  return getJson<AssetAiDraft>(`/api/assets/${encodeURIComponent(assetId)}/ai-draft${suffix}`)
}

export type CampaignAsset = {
  name?: string
  kind?: string
  platform?: string
  integration?: string
  caption?: string
  description?: string
  visualBrief?: string
  realPhotoBrief?: string
  approvalStatus?: string
  publishStatus?: string
  captionStatus?: string
  visualStatus?: string
  visualUrl?: string
  imageUrl?: string
  mediaUrl?: string
  filePath?: string
  visual_url?: string
  image_url?: string
  media_url?: string
  file_path?: string
  creative_url?: string
  image_path?: string
  publishingReferences?: Array<{ postizId?: string; mediaUrl?: string }>
}

export type ProductLineItem = {
  id?: string
  name?: string
  type?: string
  category?: string
  price_zar?: number
  price_eur?: number
  per?: string
  duration_min?: number | null
  verified?: boolean
  source?: string
  brand_id?: string
  product_brand?: string
  reference_image_ids?: string[]
}

export type ProductLineItemsPayload = {
  ok?: boolean
  brand_id?: string
  currency?: string
  market?: string
  products?: ProductLineItem[]
  count?: number
  verified_count?: number
  source?: string
  error?: string
}

export function fetchProductLineItems(brandId: string) {
  return getJson<ProductLineItemsPayload>(
    `/api/products/line-items?brand_id=${encodeURIComponent(brandId)}`,
  )
}

export type Campaign = {
  identity?: { name?: string }
  assets?: Record<string, CampaignAsset>
  error?: string
}

export function fetchCampaign(campaignId: string) {
  return getJson<Campaign>(`/api/campaigns/${encodeURIComponent(campaignId)}`)
}

const MEDIA_ROOTS = ['assets/', 'asset-media/', 'brand-images/']

export function resolveAssetUrl(raw?: string | null): string {
  const p = (raw || '').trim()
  if (!p) return ''
  if (/^(https?:|data:|blob:|file:)/i.test(p)) return p
  let s = p.replace(/^\/+/, '')
  while (s.startsWith('assets/assets/')) s = s.slice('assets/'.length)
  if (MEDIA_ROOTS.some((root) => s.startsWith(root))) return `/${s}`
  return `/assets/${s}`
}

export function assetVisualUrl(asset?: CampaignAsset | null): string {
  if (!asset) return ''
  const raw =
    asset.visualUrl ||
    asset.imageUrl ||
    asset.mediaUrl ||
    asset.visual_url ||
    asset.image_url ||
    asset.media_url ||
    asset.creative_url ||
    asset.filePath ||
    asset.file_path ||
    asset.image_path ||
    ''
  return (
    resolveAssetUrl(raw) ||
    resolveAssetUrl(asset.publishingReferences?.[0]?.mediaUrl) ||
    ''
  )
}

export function inboxItemThumbUrl(item?: InboxItem | null): string {
  const meta = item?.meta as Record<string, unknown> | undefined
  if (!meta) return ''
  const raw = String(
    meta.image_url ||
      meta.imageUrl ||
      meta.image_path ||
      meta.filePath ||
      '',
  ).trim()
  return resolveAssetUrl(raw)
}

export type InboxMediaTag = {
  id: 'has-image' | 'no-image' | 'no-brief'
  label: string
  tone: 'green' | 'mute' | 'gold'
}

export function inboxChannelLabel(item?: InboxItem | null): string {
  const meta = item?.meta
  const raw = String(meta?.primary_channel || meta?.platform || '').trim()
  if (!raw) return ''
  return raw.replace(/_/g, ' ')
}

export function inboxGoesOutIso(item?: InboxItem | null): string | null {
  const meta = item?.meta
  const raw = meta?.goes_out_at || meta?.event_date
  if (!raw) return null
  const s = String(raw).trim()
  return s || null
}

export function inboxMediaTag(item?: InboxItem | null): InboxMediaTag {
  if (inboxItemThumbUrl(item)) {
    return { id: 'has-image', label: 'Has image', tone: 'green' }
  }
  const brief = String(item?.summary || item?.meta?.caption || '').trim()
  if (!brief) return { id: 'no-brief', label: 'No brief', tone: 'gold' }
  return { id: 'no-image', label: 'No image', tone: 'mute' }
}

export type VisualLibraryPayload = {
  ok?: boolean
  images?: unknown[]
  stats?: Record<string, unknown>
  error?: string
}

export function fetchVisualLibrary(brand: string) {
  return getJson<VisualLibraryPayload>(
    `/api/visual-library/${encodeURIComponent(brand)}/images`,
  )
}

export function fetchVisualLibraryStats(brand: string) {
  return getJson<Record<string, unknown>>(
    `/api/visual-library/${encodeURIComponent(brand)}/stats`,
  )
}

export type MemeCatalogPayload = {
  ok?: boolean
  memes?: unknown[]
  templates?: unknown[]
  error?: string
}

export function fetchMemeCatalog(brand?: string) {
  const q = brand ? `?brand=${encodeURIComponent(brand)}` : ''
  return getJson<MemeCatalogPayload>(`/api/intel/memes/catalog${q}`)
}

export type PostizQueueItem = Record<string, unknown> & {
  publish_id?: string
  item_id?: string
  platform?: string
  caption_preview?: string
  scheduled_date?: string
  publish_timestamp?: string
  status?: string
  postiz_post_id?: string
}

export type PostizOverview = {
  ok?: boolean
  ts?: string
  summary?: string
  queue?: PostizQueueItem[]
  scheduled?: PostizQueueItem[]
  published?: PostizQueueItem[]
  queue_total?: number
  scheduled_total?: number
  published_total?: number
  dedup?: { queue_hidden_shipped?: number }
  note?: string
  error?: string
}

export function fetchPostizOverview() {
  return getJson<PostizOverview>('/api/intel/postiz')
}

export type PostizStatus = {
  ok?: boolean
  api_key_present?: boolean
  oauth_client_id_present?: boolean
  oauth_client_secret_present?: boolean
  api_base?: string
  last_check?: string
  oauth_token_brands?: Array<Record<string, unknown>>
  error?: string
}

export async function fetchPostizStatus(): Promise<PostizStatus & { httpStatus?: number }> {
  const res = await fetch('/api/postiz/status', { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json()) as PostizStatus
  return { ...data, httpStatus: res.status }
}

export type PostizChannels = {
  ok?: boolean
  channels?: Array<{ id?: string; provider?: string; name?: string; disabled?: boolean }>
  count?: number
  error?: string
}

export async function fetchPostizChannels(): Promise<PostizChannels & { httpStatus?: number }> {
  const res = await fetch('/api/postiz/channels', { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json()) as PostizChannels
  return { ...data, httpStatus: res.status }
}

export type PublishMode = {
  ok?: boolean
  mode?: string
  label?: string
  hint?: string
  auto_release?: boolean
  auto_release_hour?: number
  auto_release_source?: string
}

export function fetchPublishMode() {
  return getJson<PublishMode>('/api/publish/mode')
}

export type PublishSandboxSummary = {
  ok?: boolean
  mode?: string
  queue_depth?: number
  receipt_count?: number
  last_receipt_at?: string
}

export function fetchPublishSandboxSummary() {
  return getJson<PublishSandboxSummary>('/api/publish/sandbox/summary')
}

export type SandboxQueueItem = {
  queue_id?: string
  idempotency_key?: string
  brand_id?: string
  platform?: string
  channel?: string
  caption?: string
  caption_preview?: string
  status?: string
  human_approved?: boolean
  created_at?: string
  would_publish_at?: string
  lodged_title?: string
  event_date?: string
  asset_id?: string
  campaign_id?: string
  inbox_item_id?: string
  image_url?: string
  image_path?: string
}

export type SandboxQueuePayload = {
  ok?: boolean
  mode?: string
  items?: SandboxQueueItem[]
  total_pending?: number
}

export function fetchSandboxQueue(brand?: string, limit?: number) {
  const q = new URLSearchParams()
  if (brand) q.set('brand', brand)
  if (limit != null) q.set('limit', String(limit))
  const suffix = q.toString() ? `?${q}` : ''
  return getJson<SandboxQueuePayload>(`/api/publish/sandbox/queue${suffix}`)
}

export type PostizPostActionResult = {
  ok?: boolean
  partial?: boolean
  error?: string
}

async function postJsonWithStatus<T>(path: string, body: unknown): Promise<{ status: number; data: T }> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json().catch(() => ({}))) as T
  return { status: res.status, data }
}

export function enqueueSandboxItem(body: {
  brand_id: string
  asset_id?: string
  platform?: string
  caption_preview?: string
  inbox_item_id?: string
  idempotency_key?: string
}) {
  return postJsonWithStatus<{ ok?: boolean; item?: SandboxQueueItem; error?: string }>(
    '/api/publish/sandbox/enqueue',
    body,
  )
}

export function cancelPostizPost(postId: string, reason: string) {
  return postJsonWithStatus<PostizPostActionResult>(
    `/api/postiz/posts/${encodeURIComponent(postId)}/cancel`,
    { reason: reason.slice(0, 200) },
  )
}

export function reschedulePostizPost(postId: string, scheduledAt: string, content?: string) {
  const body: { scheduledAt: string; content?: string } = { scheduledAt }
  if (content) body.content = content
  return postJsonWithStatus<PostizPostActionResult>(
    `/api/postiz/posts/${encodeURIComponent(postId)}/reschedule`,
    body,
  )
}

export type GbpStatus = {
  ok?: boolean
  credentials_present?: boolean
  scopes?: string[]
  tokens_per_brand?: Record<string, unknown>
  error?: string
}

export async function fetchGbpStatus(): Promise<GbpStatus & { httpStatus?: number }> {
  const res = await fetch('/api/gbp/status', { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json()) as GbpStatus
  return { ...data, httpStatus: res.status }
}

export type GbpSuggestions = {
  ok?: boolean
  ts?: string
  input?: Record<string, unknown>
  last_post?: Record<string, unknown>
}

export function fetchGbpSuggestions() {
  return getJson<GbpSuggestions>('/api/intel/gbp_suggestions')
}

export type GbpPlan = Record<string, unknown>

export function fetchGbpPlans(brandId: string, limit = 30) {
  const q = new URLSearchParams({ brand_id: brandId, limit: String(limit) })
  return getJson<{ ok?: boolean; plans?: GbpPlan[]; count?: number }>(
    `/api/gbp/daily-poster/plans?${q}`,
  )
}

export async function fetchGbpLatestPlan(brandId: string) {
  const q = new URLSearchParams({ brand_id: brandId })
  const res = await fetch(`/api/gbp/daily-poster/latest?${q}`, { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  return { status: res.status, data }
}

export type GbpDailyPosterBody = {
  brand_id: string
  days?: number
  posts_per_day?: number
}

export function previewGbpDailyPlan(body: GbpDailyPosterBody) {
  return postJson<Record<string, unknown>>('/api/gbp/daily-poster/preview', body)
}

export function publishGbpDailyPlan(body: GbpDailyPosterBody) {
  return postJson<Record<string, unknown>>('/api/gbp/daily-poster/publish', body)
}

export type GmbDraft = {
  id?: string
  title?: string
  body?: string
  cta?: string
  link?: string
  imageUrl?: string
  brand?: string
}

export function fetchGmbDrafts() {
  return getJson<{ ok?: boolean; drafts?: GmbDraft[]; count?: number }>('/api/intel/gmb/drafts')
}

export function createGmbDraft(body: GmbDraft) {
  return postJson<{ ok?: boolean; draft?: GmbDraft }>('/api/intel/gmb/drafts', body)
}

export function updateGmbDraft(id: string, body: GmbDraft) {
  return fetch(`/api/intel/gmb/draft/${encodeURIComponent(id)}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (res) => {
    if (res.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
      throw new Error('auth required')
    }
    if (!res.ok) throw new Error(`${res.status}`)
    return res.json() as Promise<{ ok?: boolean; draft?: GmbDraft }>
  })
}

export type SocialsStatus = {
  ok?: boolean
  graph_configured?: boolean
  oembed_reachable?: boolean
  ig_account_id?: string | null
  reason?: string | null
}

export function fetchSocialsStatus() {
  return getJson<SocialsStatus>('/api/socials/status')
}

export type SocialPost = {
  id?: string
  caption?: string
  media_type?: string
  media_url?: string
  thumbnail_url?: string
  permalink?: string
  timestamp?: string
  like_count?: number
  comments_count?: number
  source?: string
  oembed_html?: string
  oembed_author?: string
  oembed_thumbnail?: string
}

export type SocialsPostsPayload = {
  data?: SocialPost[]
  paging?: { next_cursor?: string | null; has_more?: boolean }
  _meta?: {
    total_returned?: number
    days_covered?: number
    oldest?: string | null
    newest?: string | null
    sources?: Record<string, number>
    graph_error?: string | null
  }
}

export function fetchSocialsPosts(opts: { days?: number; limit?: number; after?: string }) {
  const q = new URLSearchParams()
  if (opts.days != null) q.set('days', String(opts.days))
  if (opts.limit != null) q.set('limit', String(opts.limit))
  if (opts.after) q.set('after', opts.after)
  return getJson<SocialsPostsPayload>(`/api/socials/posts?${q}`)
}

export type SocialsOembed = {
  ok?: boolean
  html?: string
  author_name?: string
  thumbnail_url?: string
  provider?: string
  type?: string
  version?: string
  error?: string
}

export async function fetchSocialsOembed(url: string): Promise<SocialsOembed & { httpStatus?: number }> {
  const q = new URLSearchParams({ url })
  const res = await fetch(`/api/socials/oembed?${q}`, { credentials: 'same-origin' })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json().catch(() => ({}))) as SocialsOembed
  return { ...data, httpStatus: res.status }
}

export async function deleteGmbDraft(id: string) {
  const res = await fetch(`/api/intel/gmb/draft/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  return res.json() as Promise<{ ok?: boolean; deleted?: boolean }>
}

export async function scheduleGmbDraft(id: string) {
  const res = await fetch(`/api/intel/gmb/draft/${encodeURIComponent(id)}/schedule`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  return { status: res.status, data }
}
