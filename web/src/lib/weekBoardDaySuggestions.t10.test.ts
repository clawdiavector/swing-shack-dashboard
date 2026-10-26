import { describe, expect, it } from 'vitest'
import { postsByDayForSuggestions } from './weekBoardDaySuggestions'

describe('postsByDayForSuggestions (T10)', () => {
  it('fills the day from week posts when the API map is empty', () => {
    const out = postsByDayForSuggestions(
      '2027-03-14',
      [{ calendar_id: 'c1', title: 'Vice Pro Air', state: 'draft_ready' }],
      {},
    )
    expect(out['2027-03-14']).toEqual([{ calendar_id: 'c1', title: 'Vice Pro Air', state: 'draft_ready' }])
  })

  it('keeps API primary rows when present', () => {
    const api = { '2027-03-14': [{ title: 'From API', state: 'scheduled' }] }
    const out = postsByDayForSuggestions('2027-03-14', [{ title: 'From week', state: 'draft_ready' }], api)
    expect(out).toBe(api)
  })
})
