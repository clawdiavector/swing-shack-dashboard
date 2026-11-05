import { describe, expect, it } from 'vitest'
import { dayLabel, matchSentence, spikeSentence } from './trafficSummary'

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
