import { describe, expect, it } from 'vitest'
import { dayLabel, matchSentence, pageLabel, spikeSentence, trafficSentence, windowLabel } from './trafficSummary'

describe('windowLabel', () => {
  it('turns the analytics window into short dates', () => {
    expect(windowLabel('2026-10-28 to 2026-11-04')).toBe('28 Oct to 4 Nov')
  })
  it('returns empty for missing or odd input', () => {
    expect(windowLabel(undefined)).toBe('')
    expect(windowLabel('last week')).toBe('')
  })
})

describe('pageLabel', () => {
  it('names the home page', () => {
    expect(pageLabel('/')).toBe('Home page')
  })
  it('makes a readable name from the path', () => {
    expect(pageLabel('/bookings/')).toBe('Bookings')
    expect(pageLabel('/customer-portal/')).toBe('Customer portal')
  })
  it('shortens long article slugs', () => {
    const out = pageLabel('/takomo-irons-south-africa-are-they-actually-worth-it/')
    expect(out.length).toBeLessThanOrEqual(48)
    expect(out.startsWith('Takomo irons')).toBe(true)
  })
})

describe('trafficSentence', () => {
  it('says visits and period in plain words', () => {
    expect(trafficSentence(834, '2026-10-28 to 2026-11-04')).toBe(
      'Your website had 834 visits between 28 Oct and 4 Nov.',
    )
  })
  it('works without a window', () => {
    expect(trafficSentence(834, undefined)).toBe('Your website had 834 visits in the latest week.')
  })
  it('is empty when there is no number', () => {
    expect(trafficSentence(undefined, '2026-10-28 to 2026-11-04')).toBe('')
  })
})

describe('dayLabel', () => {
  it('gives weekday and short date', () => {
    expect(dayLabel('2026-11-03')).toBe('Tue 3 Nov')
    expect(dayLabel(undefined)).toBe('')
  })
})

describe('matchSentence', () => {
  it('says visits against the usual day, in plain words', () => {
    expect(matchSentence({ date: '2026-11-03', ga4_sessions_on_day: 120, ga4_sessions_baseline: 40, lift_pct: 200 })).toBe(
      'Tue 3 Nov: 120 visits, against about 40 on a usual day (3× as many).',
    )
  })
  it('uses percent when the lift is under double', () => {
    expect(matchSentence({ date: '2026-11-03', ga4_sessions_on_day: 64, ga4_sessions_baseline: 40, lift_pct: 60 })).toContain(
      '60% more',
    )
  })
})

describe('spikeSentence', () => {
  it('says there was no post that day', () => {
    expect(spikeSentence({ date: '2026-11-03', ga4_sessions_on_day: 120, ga4_sessions_baseline: 40, lift_pct: 200 })).toBe(
      'Tue 3 Nov: 120 visits, against about 40 usually. We posted nothing that day or the day before.',
    )
  })
})
