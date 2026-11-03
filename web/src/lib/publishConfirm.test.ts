import { describe, expect, it } from 'vitest'
import {
  formatPublishClock,
  publishNowConfirmText,
  publishNowControlText,
  publishNowSendAt,
  publishNowSuccessText,
  releasedCardStatus,
} from './publishConfirm'

const at1400 = new Date(2026, 9, 23, 14, 0, 0)

describe('publishNowConfirmText', () => {
  it('does not ask in sandbox', () => {
    expect(publishNowConfirmText('sandbox', 'IG · FB', 'Fitting week', at1400)).toBeNull()
  })

  it('asks in live, naming the post, channels, and the real send time', () => {
    expect(publishNowConfirmText('live', 'IG · FB', 'Fitting week', at1400)).toBe(
      'This is LIVE. "Fitting week" goes out for real to IG · FB at 14:05 (5 minutes from now). Send it?',
    )
  })

  it('asks when the mode is unknown', () => {
    expect(publishNowConfirmText(undefined, '', '', at1400)).toBe(
      'This is LIVE. this post goes out for real at 14:05 (5 minutes from now). Send it?',
    )
  })

  it('uses the viewer local clock, 24-hour, five minutes ahead', () => {
    const sendAt = publishNowSendAt(at1400)
    expect(sendAt.getTime() - at1400.getTime()).toBe(5 * 60 * 1000)
    expect(formatPublishClock(sendAt)).toBe('14:05')
    const late = new Date(2026, 9, 23, 23, 58, 0)
    expect(formatPublishClock(publishNowSendAt(late))).toBe('00:03')
  })
})

describe('publishNowSuccessText', () => {
  it('shows the effective time the API returned, in local HH:MM', () => {
    const apiTime = new Date(2026, 9, 23, 14, 5, 12)
    expect(publishNowSuccessText(apiTime.toISOString(), at1400)).toBe(
      'Goes out at 14:05 (5 minutes from now).',
    )
  })

  it('estimates now + 5 minutes when the API time is missing, and says so', () => {
    expect(publishNowSuccessText(undefined, at1400)).toBe(
      'Goes out at 14:05 (5 minutes from now). Estimated on this screen — the server did not return a time.',
    )
    expect(publishNowSuccessText('', at1400)).toContain('Estimated on this screen')
    expect(publishNowSuccessText('not-a-time', at1400)).not.toContain('right now')
  })

  it('names five minutes from now only when the server time is the +5 lead', () => {
    const later = new Date(2026, 9, 23, 16, 0, 0)
    expect(publishNowSuccessText(later.toISOString(), at1400)).toBe('Goes out at 16:00.')
    expect(publishNowSuccessText(later.toISOString(), at1400)).not.toContain('5 minutes from now')
  })
})

describe('publishNowControlText', () => {
  it('shows the +5 send time before the click, including in sandbox', () => {
    expect(publishNowControlText(at1400)).toBe('Goes out at 14:05 (5 minutes from now).')
    expect(publishNowConfirmText('sandbox', 'IG · FB', 'Fitting week', at1400)).toBeNull()
  })
})

describe('releasedCardStatus', () => {
  it('points at the Publish now button on the card', () => {
    expect(releasedCardStatus(true)).toBe(
      'Waiting to go out — the hourly job sends it at the scheduled time. Publish now is on this card.',
    )
    expect(releasedCardStatus(true)).not.toContain('Publish page')
  })

  it('does not mention Publish now when the card has no button', () => {
    expect(releasedCardStatus(false)).toBe(
      'Waiting to go out — the hourly job sends it at the scheduled time.',
    )
  })
})
