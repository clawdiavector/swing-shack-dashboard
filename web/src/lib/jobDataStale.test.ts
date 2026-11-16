import { describe, expect, it } from 'vitest'
import { staleDataNote } from './jobDataStale'

// Audit 3 Nov 2026: ga4_report said OK while its data was 46 days old.
describe('staleDataNote', () => {
  it('says the job runs but its data is old', () => {
    expect(staleDataNote({ data_stale: true, data: { file: 'ga4-metrics.json', age_days: 45.9 } })).toBe(
      'Runs OK, but its data is 46 days old (ga4-metrics.json).',
    )
    expect(staleDataNote({ data_stale: true, data: { file: 'x.json', age_days: 1 } })).toBe(
      'Runs OK, but its data is 1 day old (x.json).',
    )
  })
  it('says nothing when the data is fresh or unknown', () => {
    expect(staleDataNote({ data_stale: false, data: { file: 'x.json', age_days: 1 } })).toBe('')
    expect(staleDataNote({})).toBe('')
  })
})
