import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DayPostSuggestions } from './DayPostSuggestions'
import type { Suggestion } from '../../../lib/calendarSuggestions'

vi.mock('./MonthSuggestions', () => ({
  GhostChip: ({ s, compact }: { s: Suggestion; compact?: boolean }) => (
    <span data-testid="ghost-chip" data-compact={compact ? '1' : '0'}>
      {s.title}
    </span>
  ),
}))

const ghost: Suggestion = {
  key: 'g1',
  source: 'stock',
  title: 'Stock idea',
  date: '2027-03-14',
  end: '2027-03-14',
  tier: null,
  category: '',
  why: '',
  calendar_id: null,
}

describe('DayPostSuggestions (T10 week day)', () => {
  it('shows More ideas and compact ghosts when primary exists but chips are hidden', () => {
    render(
      <DayPostSuggestions
        iso="2027-03-14"
        postsByDay={{ '2027-03-14': [{ title: 'Vice Pro Air', state: 'draft_ready' }] }}
        ghosts={[ghost]}
        busyKey={null}
        pillars={[]}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        hidePrimaryChips
      />,
    )
    expect(screen.queryByTestId('primary-post-chip')).toBeNull()
    expect(screen.getByTestId('more-ideas-label')).toHaveTextContent('More ideas for this day')
    expect(screen.getByTestId('ghost-chip')).toHaveAttribute('data-compact', '1')
  })
})
