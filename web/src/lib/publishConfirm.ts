/** Lead Postiz requires before a send. Publish now is always inside this window. */
export const PUBLISH_NOW_LEAD_MINUTES = 5

/** The send time Publish now will use: now plus the same 5-minute lead the server applies. */
export function publishNowSendAt(now: Date = new Date()): Date {
  return new Date(now.getTime() + PUBLISH_NOW_LEAD_MINUTES * 60_000)
}

/** Viewer's local time, 24-hour HH:MM. */
export function formatPublishClock(when: Date): string {
  const hh = String(when.getHours()).padStart(2, '0')
  const mm = String(when.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

/** True when `when` is the same minute as now + the 5-minute lead. */
function isPublishNowLead(when: Date, now: Date): boolean {
  const lead = publishNowSendAt(now)
  return (
    formatPublishClock(when) === formatPublishClock(lead) &&
    Math.abs(when.getTime() - lead.getTime()) < 60_000
  )
}

function goesOutAtLine(when: Date, now: Date): string {
  const clock = formatPublishClock(when)
  if (isPublishNowLead(when, now)) return `Goes out at ${clock} (5 minutes from now).`
  return `Goes out at ${clock}.`
}

/** Send time on the Publish now control, before the click. Always the +5 lead. */
export function publishNowControlText(now: Date = new Date()): string {
  return goesOutAtLine(publishNowSendAt(now), now)
}

/**
 * Released week-card status. Names Publish now only when that button is on the card.
 */
export function releasedCardStatus(hasPublishNow: boolean): string {
  const wait = 'Waiting to go out — the hourly job sends it at the scheduled time.'
  if (!hasPublishNow) return wait
  return `${wait} Publish now is on this card.`
}

/** Text for the "really send?" prompt, or null when Publish now is safe to fire (sandbox). */
export function publishNowConfirmText(
  mode: string | null | undefined,
  channels: string,
  title: string,
  now: Date = new Date(),
): string | null {
  if ((mode || '').toLowerCase() === 'sandbox') return null
  const where = channels ? ` to ${channels}` : ''
  const what = title ? `"${title}"` : 'this post'
  const when = formatPublishClock(publishNowSendAt(now))
  return `This is LIVE. ${what} goes out for real${where} at ${when} (5 minutes from now). Send it?`
}

/**
 * Success note after Publish now.
 * `publishAt` is the ISO the API returned from scheduled_at_least.
 * When that is missing, use the same client +5 minute time and say so.
 */
export function publishNowSuccessText(
  publishAt: string | null | undefined,
  now: Date = new Date(),
): string {
  const parsed = publishAt ? new Date(publishAt) : null
  if (parsed && !Number.isNaN(parsed.getTime())) {
    return goesOutAtLine(parsed, now)
  }
  return `${publishNowControlText(now)} Estimated on this screen — the server did not return a time.`
}
