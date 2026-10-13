import { describe, expect, it } from 'vitest'
import { alertAction, alertHeadline, type CalendarAlert } from './calendarAlerts'

const a = (level: 'scream' | 'warn'): CalendarAlert => ({
  event_key: 'k',
  name: 'Heritage Day',
  date: '2026-10-20',
  days: 7,
  tier: 'A-PIN',
  level,
  state: 'no_plan',
  brief_id: null,
  plan_id: null,
  brand_id: 'stick',
  message: '',
})

describe('alertHeadline', () => {
  it('is empty with nothing to say', () => {
    expect(alertHeadline([])).toBe('')
  })
  it('counts only the loud ones when any are loud', () => {
    expect(alertHeadline([a('scream'), a('warn')])).toBe('1 approved date is close and not ready')
    expect(alertHeadline([a('scream'), a('scream')])).toBe('2 approved dates are close and not ready')
  })
  it('is calmer when none are loud', () => {
    expect(alertHeadline([a('warn')])).toBe('1 approved date coming up with nothing ready yet')
  })
})

describe('alertAction', () => {
  it('makes a plan only when there is none', () => {
    expect(alertAction('no_plan')).toBe('Make a plan')
    expect(alertAction('plan_draft')).toBe('Open the plan')
    expect(alertAction('plan_approved')).toBe('Open the plan')
  })
})
