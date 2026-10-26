import { describe, expect, it } from 'vitest'
import { suggestionsUnderPrimary, type Suggestion } from './calendarSuggestions'

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

describe('suggestionsUnderPrimary (T10)', () => {
  it('keeps ghosts as main when the day has no post', () => {
    const ghosts = [s('a', '2027-03-14')]
    const r = suggestionsUnderPrimary('2027-03-14', {}, ghosts)
    expect(r.primary).toEqual([])
    expect(r.secondary).toEqual(ghosts)
    expect(r.showMoreLabel).toBe(false)
  })
  it('labels secondary suggestions when a post is already on the day', () => {
    const posts = { '2027-03-14': [{ title: 'Vice Pro Air', state: 'draft_ready' }] }
    const ghosts = [s('a', '2027-03-14')]
    const r = suggestionsUnderPrimary('2027-03-14', posts, ghosts)
    expect(r.primary[0]?.title).toBe('Vice Pro Air')
    expect(r.showMoreLabel).toBe(true)
  })
})
