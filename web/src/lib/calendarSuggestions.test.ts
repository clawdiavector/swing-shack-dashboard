import { describe, expect, it } from 'vitest'
import { groupByDay, spanLabel, undoMessage, type Suggestion } from './calendarSuggestions'
import { pillarForKey } from '../pages/calendar/planning/TriagePanel'

const s = (key: string, date: string): Suggestion => ({
  key,
  source: 'date',
  title: key,
  date,
  end: date,
  tier: null,
  category: '',
  why: '',
  calendar_id: null,
})

describe('groupByDay', () => {
  it('puts each suggestion on its day', () => {
    const g = groupByDay([s('a', '2027-03-14'), s('b', '2027-03-14'), s('c', '2027-03-21')])
    expect(Object.keys(g)).toEqual(['2027-03-14', '2027-03-21'])
    expect(g['2027-03-14'].map((x) => x.key)).toEqual(['a', 'b'])
  })
})

describe('spanLabel', () => {
  it('is one day, a span in a month, or a span across months', () => {
    expect(spanLabel('2027-03-14', '2027-03-14')).toBe('14 Mar')
    expect(spanLabel('2027-03-14', '')).toBe('14 Mar')
    expect(spanLabel('2027-03-14', '2027-03-21')).toBe('14 – 21 Mar')
    expect(spanLabel('2027-03-28', '2027-04-02')).toBe('28 Mar – 2 Apr')
  })
})

describe('pillarForKey', () => {
  const pillars = [
    { pillar_id: 'stick-retail', name: 'Retail' },
    { pillar_id: 'stick-fitting', name: 'Fitting' },
    { pillar_id: 'stick-coaching', name: 'Coaching' },
  ]
  it('maps 1, 2, 3 to the pillars in order, and nothing else', () => {
    expect(pillarForKey('1', pillars)?.pillar_id).toBe('stick-retail')
    expect(pillarForKey('3', pillars)?.pillar_id).toBe('stick-coaching')
    expect(pillarForKey('4', pillars)).toBeNull()
    expect(pillarForKey('0', pillars)).toBeNull()
    expect(pillarForKey('r', pillars)).toBeNull()
    expect(pillarForKey('11', pillars)).toBeNull()
    expect(pillarForKey('1', [])).toBeNull()
  })
})

describe('undoMessage', () => {
  it('says what happened', () => {
    expect(undoMessage('approve', 'Cape Epic')).toBe('Added “Cape Epic” to the calendar.')
    expect(undoMessage('reject', 'Cape Epic')).toBe('Removed “Cape Epic”.')
    expect(undoMessage('later', 'Cape Epic')).toBe('Put off “Cape Epic” for two weeks.')
  })
})
