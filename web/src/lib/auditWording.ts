// Plain wording for spots the 3 Nov 2026 audit found reading wrong or in engineer words.
import type { CalendarAlert } from './calendarAlerts'

/** Publish page intro. A live queue is not a sandbox. */
export function publishIntro(mode: string | null | undefined): string {
  if (mode === 'live') {
    return 'Posts approved and queued to go out: image, caption, platform. Publish now sends them to the platforms for real.'
  }
  return 'Sandbox publish queue — image, caption, platform. Approve on Review does not publish live.'
}

/** Scheduled page intro, by publish mode and auto-release. */
export function shelfIntro(mode: string | null | undefined, autoRelease: boolean | null | undefined): string {
  if (mode !== 'live') {
    return 'Approved posts with a go-live date. Release them when you’re ready. Sandbox (practice mode) only until Kyle switches on live.'
  }
  return autoRelease
    ? 'Approved posts with a go-live date. Each one releases automatically on its day. Release now sends one sooner.'
    : 'Approved posts with a go-live date. Auto-release is off, so each one waits until you press Release now.'
}

/** Under the alert headline: the rows it does not count, so the number matches the list. */
export function alertMoreLine(alerts: CalendarAlert[]): string {
  const loud = alerts.filter((a) => a.level === 'scream').length
  const rest = alerts.length - loud
  if (!loud || !rest) return ''
  return `and ${rest} more coming up with nothing ready yet`
}

/** "PHOTO-POST" → "Layout: Photo post". */
export function templateTagText(label: string): string {
  const words = label.replace(/[-_]+/g, ' ').trim().toLowerCase()
  return `Layout: ${words.charAt(0).toUpperCase()}${words.slice(1)}`
}

function shortCaption(caption: string, max = 40): string {
  const one = caption.replace(/\s+/g, ' ').trim()
  if (one.length <= max) return one
  const cut = one.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return `${(space > 0 ? cut.slice(0, space) : cut).replace(/[\s,.;:!?-]+$/, '')}…`
}

/** Today's "What worked" tooltip: which post it is, not only its score. */
export function workedPostTip(p: {
  verdict?: string | null
  engagementRate?: number | null
  caption?: string | null
}): string {
  const score = `${p.verdict || 'Recent post'}${p.engagementRate != null ? ` · ${p.engagementRate.toFixed(2)}% engagement` : ''}`
  const caption = (p.caption || '').trim()
  return caption ? `${score}: “${shortCaption(caption)}”. Open it in Results.` : `${score}. Open it in Results.`
}
