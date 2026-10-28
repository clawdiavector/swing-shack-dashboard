import { describe, expect, it } from 'vitest'
import { brandPhotoPath, defaultGoLiveDate, slugFromCaption } from './postStudio'

describe('postStudio helpers', () => {
  it('slugFromCaption keeps words and drops punctuation', () => {
    expect(slugFromCaption('Fit first. Hit second.')).toBe('fit-first-hit-second')
  })

  it('brandPhotoPath points at the brand images folder', () => {
    expect(brandPhotoPath('stick', 'club.jpg')).toBe('data/brand-directory/stick/images/club.jpg')
  })

  it('defaultGoLiveDate returns an ISO date string', () => {
    expect(defaultGoLiveDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
