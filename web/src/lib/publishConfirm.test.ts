import { describe, expect, it } from 'vitest'
import { publishNowConfirmText } from './publishConfirm'

describe('publishNowConfirmText', () => {
  it('does not ask in sandbox', () => {
    expect(publishNowConfirmText('sandbox', 'IG · FB', 'Fitting week')).toBeNull()
  })

  it('asks in live, naming the post and channels', () => {
    expect(publishNowConfirmText('live', 'IG · FB', 'Fitting week')).toBe(
      'This is LIVE. "Fitting week" goes out for real to IG · FB right now. Send it?',
    )
  })

  it('asks when the mode is unknown', () => {
    expect(publishNowConfirmText(undefined, '', '')).toBe(
      'This is LIVE. this post goes out for real right now. Send it?',
    )
  })
})
