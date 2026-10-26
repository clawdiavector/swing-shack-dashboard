import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { nextStep, PostCard, queueDates, type PostHandlers } from './GbpPosts'

const handlers: PostHandlers = {
  onApprove: () => {},
  onUnapprove: () => {},
  onPublish: () => {},
  onDelete: () => {},
  onPhoto: () => {},
  onSave: async () => true,
}
const ready = (id: string, at: string, brand = 'stick') => ({ id, brand, status: 'approved' as const, approvedAt: at })

describe('queueDates', () => {
  it('feeds approved posts out one a day in approval order', () => {
    // Monday 26 Oct 2026, 06:00 SAST: before the 09:00 run, so the first goes out today
    const now = new Date('2026-10-26T04:00:00Z')
    const out = queueDates([ready('b', '2026-10-25T10:00:00Z'), ready('a', '2026-10-25T09:00:00Z'), ready('c', '2026-10-25T11:00:00Z')], now)
    expect(out.a).toBe('Mon 26 Oct')
    expect(out.b).toBe('Tue 27 Oct')
    expect(out.c).toBe('Wed 28 Oct')
  })
  it('starts tomorrow once the morning run has passed', () => {
    const now = new Date('2026-10-26T09:00:00Z') // 11:00 SAST
    expect(queueDates([ready('a', '2026-10-25T09:00:00Z')], now).a).toBe('Tue 27 Oct')
  })
  it('starts tomorrow when one was already sent today', () => {
    const now = new Date('2026-10-26T04:00:00Z')
    const sent = { id: 's', brand: 'stick', status: 'scheduled' as const, updatedAt: '2026-10-26T03:00:00Z' }
    expect(queueDates([sent, ready('a', '2026-10-25T09:00:00Z')], now).a).toBe('Tue 27 Oct')
  })
  it('keeps each brand in its own queue', () => {
    const now = new Date('2026-10-26T04:00:00Z')
    const out = queueDates([ready('s1', '2026-10-25T09:00:00Z', 'stick'), ready('w1', '2026-10-25T09:00:00Z', 'swing-shack')], now)
    expect(out.s1).toBe('Mon 26 Oct')
    expect(out.w1).toBe('Mon 26 Oct')
  })
})

describe('queue wording', () => {
  it('tells her one goes out a day and when the first goes', () => {
    const out = nextStep({ check: 0, ready: 12, sent: 1 }, 'Tue 27 Oct')
    expect(out).toContain('12 posts are approved and waiting')
    expect(out).toContain('One goes out each day at about 09:00, starting Tue 27 Oct')
  })
  it('shows each approved card its day', () => {
    const d = { id: 'a', title: 'T', body: 'B', cta: 'C', link: 'https://stickgolf.co.za/', imageUrl: '/x.jpg', status: 'approved' as const }
    const out = renderToStaticMarkup(<PostCard d={d} busy={false} terms={[]} handlers={handlers} goesOut="Tue 27 Oct" />)
    expect(out).toContain('Goes out on its own on Tue 27 Oct at about 09:00.')
  })
})
