import { describe, expect, it } from 'vitest'
import { captionTag } from './captionPresence'

describe('captionTag', () => {
  it('marks present captions green', () => {
    expect(captionTag({ caption_present: true })).toEqual({
      id: 'caption',
      label: 'Caption',
      tone: 'green',
    })
  })

  it('marks absent captions mute', () => {
    expect(captionTag({ caption_present: false })).toEqual({
      id: 'no-caption',
      label: 'No caption',
      tone: 'mute',
    })
  })

  it('treats missing row as no caption', () => {
    expect(captionTag(null).id).toBe('no-caption')
  })
})
