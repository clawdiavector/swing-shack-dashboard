import { describe, expect, it } from 'vitest'
import { feedJobLine } from './MonthSuggestions'

describe('feedJobLine', () => {
  it('names the job and the best time for a stock line', () => {
    expect(feedJobLine({ job_label: 'New in', best_time: '09:00-12:00' })).toBe('New in · post 09:00-12:00')
  })
  it('is empty for a suggestion without a job', () => {
    expect(feedJobLine({})).toBe('')
  })
})
