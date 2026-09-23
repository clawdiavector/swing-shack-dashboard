export type PlanningTier = 'A-PIN' | 'B-PIN' | 'C-PIN'

export type BigBrandIdea = {
  name?: string
  belief?: string
  elevator?: string
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
  monthly_theme?: string
  days?: Record<string, PlanningMonthItem[]>
  important_dates?: unknown
  lane_system?: unknown
  production_runway_note?: string
  reminder?: string
}

export type PlanningTimelineEvent = {
  id: string
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
  }[]
  deadlines?: { label?: string; due?: string }[]
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
  right_now?: { retail?: string; fitting?: string; coaching?: string }
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
}

export type PlanningEventDetail = {
  ok?: boolean
  event?: PlanningTimelineEvent
  always_on_pillars?: unknown[]
}
