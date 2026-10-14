import { describe, expect, it } from 'vitest'
import type { Plan, PlanItem } from './plan'
import { brandLabel, shootRequest, shootSteps, signOffMessage } from './planMessages'

const item = (over: Partial<PlanItem>): PlanItem => ({
  item_id: 'it-1',
  kind: 'post',
  title: 'A post',
  due: '2027-02-08',
  days_before_event: 6,
  channel: '',
  owner: 'marketing',
  note: '',
  needs_real_video: false,
  late: false,
  status: 'kept',
  source: 'template',
  ...over,
})

const photos = item({ item_id: 'p', kind: 'shoot', title: 'Shoot real photos of the products', due: '2027-02-02' })
const video = item({
  item_id: 'v',
  kind: 'shoot',
  title: 'Shoot a short real video with a person on camera',
  due: '2027-02-01',
  needs_real_video: true,
})
const boost = item({ item_id: 'b', kind: 'boost', title: 'Boost the best teaser', needs_real_video: true, budget: 1500 })

const plan = (items: PlanItem[], over: Partial<Plan> = {}): Plan => ({
  plan_id: 'pln-1',
  brand_id: 'stick',
  brief_id: 'brf-1',
  brief_status: 'approved',
  event_name: "Valentine's Day",
  event_date: '2027-02-14',
  status: 'proposed',
  event_kind: 'retail_push',
  profile: 'retail_push',
  profile_label: 'Retail push',
  items,
  ...over,
})

describe('shootSteps', () => {
  it('lists the live shoot steps only', () => {
    const p = plan([photos, video, boost, { ...item({ item_id: 'x', kind: 'shoot' }), status: 'removed' }])
    expect(shootSteps(p).map((i) => i.item_id)).toEqual(['v', 'p'])
  })
})

describe('shootRequest', () => {
  const p = plan([photos, video, boost])
  const text = shootRequest({ plan: p, steps: shootSteps(p), facility: 'Pieter', sendTo: 'Christelle on WhatsApp', today: '2026-10-14' })

  it('says what the shoot is for, by when, and where to send it', () => {
    expect(text).toContain('Hi Pieter,')
    expect(text).toContain("Valentine's Day (14 Feb 2027) at Stick")
    expect(text).toContain('please send everything by 1 Feb 2027')   // the earliest shoot step
    expect(text).toContain('Send to: Christelle on WhatsApp')
  })
  it('asks for photos and for video when the plan needs both, and tailors the photos to the type of date', () => {
    expect(text).toContain('Photos: about 10 to 15 of the products we are promoting')
    expect(text).toContain('Video: 2 or 3 short clips')
    expect(text).toContain('happy to be filmed')
  })
  it('keeps the rules: real products and spaces, no effects', () => {
    expect(text).toContain('Real products and real spaces only')
    expect(text).toContain('do not edit')
  })
  it('asks only for photos when no step needs video, and only for what is in the steps', () => {
    const t = shootRequest({ plan: plan([photos]), steps: [photos], today: '2026-10-14' })
    expect(t).toContain('Photos:')
    expect(t).not.toContain('Video:')
    expect(t).not.toContain('happy to be filmed')
    expect(t.startsWith('Hi,')).toBe(true)
  })
  it('does not invent a place to send to, and says so when a date has gone', () => {
    const t = shootRequest({ plan: p, steps: shootSteps(p), today: '2027-02-05' })
    expect(t).toContain('Send to: [where to send it]')
    expect(t).toContain('as soon as you can')
    expect(t).not.toContain('please send everything by')
  })
  it('uses the type of date, not the plan shape, for what to photograph', () => {
    const sport = plan([photos], { event_kind: 'sport_event', profile: 'light' })
    expect(shootRequest({ plan: sport, steps: [photos], today: '2026-10-14' })).toContain('the bays, the gear, the screens')
  })
})

describe('signOffMessage', () => {
  const p = plan([photos, video, boost, item({ item_id: 'g', kind: 'post', title: 'Teaser post', due: '2027-02-08' })])
  const text = signOffMessage({ plan: p, to: 'Kyle', from: 'Christelle', today: '2026-10-14' })

  it('names the date, the brand and the shape, and lists every step in date order', () => {
    expect(text).toContain("plan for Valentine's Day (14 Feb 2027) at Stick, shaped as Retail push")
    const order = ['1 Feb 2027', '2 Feb 2027', '8 Feb 2027'].map((d) => text.indexOf(`• ${d}`))
    expect(order.every((n) => n > -1)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
  })
  it('shows the boost budget and says nothing is spent', () => {
    expect(text).toContain('Boost budget in the plan: R1 500')
    expect(text).toContain('Nothing is spent until we say so.')
  })
  it('asks a clear question and signs off', () => {
    expect(text).toContain('Reply "OK"')
    expect(text.trim().endsWith('Thanks, Christelle')).toBe(true)
  })
  it('leaves out removed steps and says when a boost has no budget', () => {
    const q = plan([{ ...photos, status: 'removed' }, { ...boost, budget: null }])
    const t = signOffMessage({ plan: q, today: '2026-10-14' })
    expect(t).not.toContain('Shoot real photos')
    expect(t).toContain('no budget set yet')
    expect(t.startsWith('Hi,')).toBe(true)
  })
})

describe('brandLabel', () => {
  it('uses the brand name people use', () => {
    expect(brandLabel('swing-shack')).toBe('Swing Shack')
    expect(brandLabel('unknown-brand')).toBe('unknown-brand')
  })
})
