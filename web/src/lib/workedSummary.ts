import type { InsightPost, LearnHeadline } from './api'

/** Samples needed before the learn job can call a pattern. */
export const SAMPLES_NEEDED = 10

export function postFormat(mediaType?: string): string {
  const t = (mediaType || '').toUpperCase()
  if (t === 'VIDEO') return 'Reel'
  if (t === 'CAROUSEL_ALBUM') return 'Carousel'
  if (t === 'IMAGE') return 'Photo'
  return 'Post'
}

export function postWeekday(timestamp?: string): string {
  if (!timestamp) return ''
  const d = new Date(timestamp)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-ZA', { weekday: 'long', timeZone: 'Africa/Johannesburg' })
}

/** Whole-number multiple of the median, or null when it is not a real lead (under 1.5×). */
export function timesAverage(rate?: number, average?: number): number | null {
  if (rate == null || !average || average <= 0) return null
  const x = rate / average
  return x >= 1.5 ? Math.round(x) : null
}

type BestPost = Pick<InsightPost, 'engagementRate' | 'media_type' | 'timestamp'>

export function bestPostSentence(posts: BestPost[], average?: number): string {
  const best = posts[0]
  if (!best || best.engagementRate == null) return ''
  const rate = `${best.engagementRate.toFixed(1)}%`
  const x = timesAverage(best.engagementRate, average)
  if (x == null) return `Nothing stands out yet: the top post got ${rate} engagement, close to a typical post.`
  const format = postFormat(best.media_type).toLowerCase()
  const day = postWeekday(best.timestamp)
  const when = day ? ` on a ${day}` : ''
  return `Your best post got ${rate} engagement, about ${x}× a typical post. It was a ${format}${when}. Do more like it.`
}

export function learnSentence(h: LearnHeadline): string {
  const winners = h.winners ?? 0
  const samples = h.samples ?? 0
  if (winners > 0) {
    return `${winners} winning ${winners === 1 ? 'post' : 'posts'} found so far, from ${samples} scored.`
  }
  if (samples < SAMPLES_NEEDED) {
    return `Too early to call a pattern. We need about ${SAMPLES_NEEDED} scored posts and have ${samples}.`
  }
  return `${samples} posts scored, but none stood out as a winner yet.`
}
