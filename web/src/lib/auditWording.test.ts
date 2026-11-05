import { describe, expect, it } from 'vitest'
import { gbpPausedSince, nextStep } from '../components/GbpPosts'
import {
  alertMoreLine,
  publishIntro,
  shelfIntro,
  templateTagText,
  workedPostTip,
} from './auditWording'
import type { CalendarAlert } from './calendarAlerts'

const alert = (level: 'scream' | 'warn'): CalendarAlert => ({
  event_key: 'k',
  name: 'Polo season.',
  date: '2026-11-15',
  days: 10,
  tier: 'A-PIN',
  level,
  state: 'no_plan',
  brief_id: null,
  plan_id: null,
  brand_id: 'stick',
  message: '',
})

describe('publishIntro', () => {
  it('does not call a live queue a sandbox', () => {
    const live = publishIntro('live')
    expect(live).not.toMatch(/sandbox/i)
    expect(live).toContain('for real')
  })
  it('keeps the practice wording in sandbox mode', () => {
    expect(publishIntro('sandbox')).toMatch(/sandbox/i)
    expect(publishIntro(undefined)).toMatch(/sandbox/i)
  })
})

describe('shelfIntro', () => {
  it('says posts release on their day when live and auto-release is on', () => {
    const out = shelfIntro('live', true)
    expect(out).not.toMatch(/sandbox|Kyle/i)
    expect(out).toContain('automatically')
  })
  it('asks for Release now when live and auto-release is off', () => {
    const out = shelfIntro('live', false)
    expect(out).not.toMatch(/sandbox|Kyle/i)
    expect(out).toContain('Release now')
  })
  it('keeps the practice wording in sandbox mode', () => {
    expect(shelfIntro('sandbox', false)).toMatch(/sandbox/i)
  })
})

describe('alertMoreLine', () => {
  it('counts the rows the loud headline leaves out', () => {
    const rows = [alert('scream'), alert('scream'), ...Array.from({ length: 7 }, () => alert('warn'))]
    expect(alertMoreLine(rows)).toBe('and 7 more coming up with nothing ready yet')
    expect(alertMoreLine([alert('scream'), alert('warn')])).toBe('and 1 more coming up with nothing ready yet')
  })
  it('says nothing when the headline already counts every row', () => {
    expect(alertMoreLine([alert('scream'), alert('scream')])).toBe('')
    expect(alertMoreLine([alert('warn'), alert('warn')])).toBe('')
    expect(alertMoreLine([])).toBe('')
  })
})

describe('templateTagText', () => {
  it('names the layout in plain words, not an engineer code', () => {
    expect(templateTagText('PHOTO-POST')).toBe('Layout: Photo post')
    expect(templateTagText('photo-band-post')).toBe('Layout: Photo band post')
    expect(templateTagText('service_frame')).toBe('Layout: Service frame')
    expect(templateTagText('PHOTO-POST')).not.toMatch(/tpl/i)
  })
})

describe('workedPostTip', () => {
  it('names the post so you know which one it is', () => {
    const out = workedPostTip({ verdict: 'Top performer', engagementRate: 5.73, caption: 'On air with SAUMA HD RADIO 🔥 come and say hi' })
    expect(out).toContain('Top performer · 5.73% engagement')
    expect(out).toContain('“On air with SAUMA HD RADIO')
    expect(out).toContain('Open it in Results.')
  })
  it('shortens a long caption on a word', () => {
    const out = workedPostTip({ verdict: 'Above average', caption: 'Want to elevate your golfing game with something cool and new this weekend at the venue' })
    expect(out).toMatch(/“Want to elevate your golfing game with…”/)
  })
  it('still reads without a caption', () => {
    expect(workedPostTip({ verdict: null, engagementRate: null })).toBe('Recent post. Open it in Results.')
  })
})

describe('GBP paused wording', () => {
  const now = new Date('2026-11-05T08:00:00Z')
  const job = (age: number | null, at: string | null) => ({
    name: 'gbp_publish',
    brands: [{ brand: 'stick', last_success_age_h: age, last_success_at: at }],
  })

  it('is paused when the daily send has not run for two days', () => {
    expect(gbpPausedSince({ jobs: { gbp_publish: job(161, '2026-10-29T13:57:07Z') } }, 'stick', now)).toBe('Thu 29 Oct')
    expect(gbpPausedSince({ jobs: [job(161, '2026-10-29T13:57:07Z')] }, 'stick', now)).toBe('Thu 29 Oct')
  })
  it('is paused when it has never sent', () => {
    expect(gbpPausedSince({ jobs: [job(null, null)] }, 'stick', now)).toBe('never')
  })
  it('is not paused when it sent recently, or when the status is unknown', () => {
    expect(gbpPausedSince({ jobs: [job(20, '2026-11-04T12:00:00Z')] }, 'stick', now)).toBe('')
    expect(gbpPausedSince(null, 'stick', now)).toBe('')
    expect(gbpPausedSince({ jobs: [] }, 'stick', now)).toBe('')
  })
  it('stops promising a post a day while paused', () => {
    const out = nextStep({ check: 0, ready: 5, sent: 7 }, 'Wed 4 Nov', 'Thu 29 Oct')
    expect(out).toContain('5 posts are approved and waiting')
    expect(out).toContain('paused')
    expect(out).toContain('Thu 29 Oct')
    expect(out).not.toContain('One goes out each day')
  })
  it('says it has never sent when paused from the start', () => {
    expect(nextStep({ check: 0, ready: 1, sent: 0 }, undefined, 'never')).toContain('has not sent any yet')
  })
})
