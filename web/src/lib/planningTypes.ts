export type PlanningTier = 'A-PIN' | 'B-PIN' | 'C-PIN'

export type BigBrandIdea = {
  name?: string
  belief?: string
  elevator?: string
}

export type MonthlyTheme = {
  month?: string
  theme?: string
  question?: string
  supported_bet?: string
  what_we_prove?: string
  what_changes_it?: string
  lanes_emphasis?: string[]
  set_at?: string
}

export type PlanningMonthItem = {
  title?: string
  subtitle?: string
  lane?: string
  status?: string
  channel?: string
  cta?: string
  purpose?: string
  property?: string
  hook?: string
  is_paid_supported?: boolean
  stock_refs?: string[]
}

export type PlanningMonthView = {
  ok?: boolean
  monthly_theme?: string | MonthlyTheme | null
  days?: Record<string, PlanningMonthItem[]>
  important_dates?: unknown
  lane_system?: unknown
  production_runway_note?: string
  reminder?: string
}

export type PlanningTimelineEvent = {
  id: string
  event_key?: string
  /** Operator-typed entries only: campaign | moment | content | reminder. */
  type?: string
  /** Set on posts the scheduler put on the calendar, e.g. "stick-shop-corner". */
  post_type?: string
  /** Brief already written for this entry, '' when none (range timeline only). */
  brief_id?: string
  name?: string
  tier?: PlanningTier | string
  category?: string
  start?: string
  end?: string
  public_peak?: string
  planning_start?: string
  shopping_moment?: boolean
  commercial_push?: string
  pillars?: { retail?: string; fitting?: string; coaching?: string }
  lanes?: Record<string, string>
  phases?: {
    label?: string
    task?: string
    start?: string
    weeks_before_peak?: number
    verified?: boolean
    kind?: 'verified' | 'suggested_planning_date'
  }[]
  deadlines?: { label?: string; due?: string }[]
  planning_state?: 'not_planned' | 'in_flight' | 'suggested_only' | 'completed' | null
}

export type PlanningTimeline = {
  ok?: boolean
  always_on_pillars?: { name?: string; current_push_summary?: string; purpose?: string }[]
  events?: PlanningTimelineEvent[]
  tier_counts?: Record<string, number>
  shopping_moment_count?: number
}

export type PlanningRightNow = {
  ok?: boolean
  today?: string
  right_now?: { [k: string]: string | undefined; retail?: string; fitting?: string; coaching?: string }
  active_a_pins?: PlanningTimelineEvent[]
  active_b_pins?: PlanningTimelineEvent[]
  active_a_count?: number
  active_b_count?: number
  next_major_deadline?: { event_name?: string; label?: string; due?: string }
  upcoming_deadlines?: unknown[]
}

export type PlanningBigIdeaResponse = {
  ok?: boolean
  big_brand_idea?: BigBrandIdea
  north_star?: { statement?: string; source?: string } | null
  operating_goals?: Array<{
    id: string
    label: string
    metric: string
    category?: string
    outcome_measurement?: string
    connector_status?: string
    marketing_support_signal?: string
    do_not_fabricate_progress?: boolean
    source?: string
    // V2.11 — when a goal is superseded_by a canonical V2.11 immediate
    // goal, the planner React component filters it out of the rendered
    // tiles. The data is preserved for audit trail.
    superseded_by?: string
    superseded_at?: string
    superseded_reason?: string
  }>
  operating_areas?: Array<{ key: string; lane?: string; tagline?: string }>
  monthly_themes?: unknown[]
  active_campaigns?: unknown[]
  lane_system?: unknown[]
  brand_id?: string
}

export type PlanningEventDetail = {
  ok?: boolean
  event?: PlanningTimelineEvent
  always_on_pillars?: unknown[]
}

export type PlanningWaitingSuggestion = {
  candidate_id: string
  title: string
  date?: string | null
  end_date?: string | null
  type?: string
  pillars?: string[]
  why_it_matters?: string | null
  created_at?: string | null
}

export type PlanningWaiting = {
  ok?: boolean
  count?: number
  suggestions?: PlanningWaitingSuggestion[]
}
