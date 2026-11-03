import type { DayPrimaryPost } from './calendarSuggestions'

type WeekDayPost = {
  calendar_id?: string | null
  title?: string | null
  state?: string
}

/** Merge week-board post cards with API posts_by_day for suggestion layout. */
export function postsByDayForSuggestions(
  dateIso: string,
  weekPosts: WeekDayPost[],
  postsByDay: Record<string, DayPrimaryPost[]>,
): Record<string, DayPrimaryPost[]> {
  const apiPrimary = postsByDay[dateIso]
  if (apiPrimary?.length) return postsByDay
  if (weekPosts.length === 0) return postsByDay
  return {
    ...postsByDay,
    [dateIso]: weekPosts.map((p) => ({
      calendar_id: p.calendar_id,
      title: String(p.title ?? '').trim(),
      state: p.state,
    })),
  }
}
