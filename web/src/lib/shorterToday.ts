// Helpers for the shorter Today page (audit, 5 Nov 2026).
import type { CalendarAlert } from './calendarAlerts'

/** The first `limit` alerts (already soonest first) and how many are left out. */
export function splitAlerts(alerts: CalendarAlert[], limit?: number): { shown: CalendarAlert[]; more: number } {
  if (!limit || alerts.length <= limit) return { shown: alerts, more: 0 }
  return { shown: alerts.slice(0, limit), more: alerts.length - limit }
}
