import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { DailyBrandSocials } from '../components/DailyBrandSocials'

const STICK_URLS = [
  'https://www.instagram.com/stick.paarl/',
  'https://www.facebook.com/profile.php?id=61585032821622',
  'https://www.youtube.com/@stickSouthAfrica',
  'https://www.tiktok.com/@stick.paarl',
  'https://share.google/FatzTjieRqyHejL1z',
]

describe('DailyBrandSocials', () => {
  it('renders all five stick profile urls', () => {
    const html = renderToStaticMarkup(
      DailyBrandSocials({
        rows: [
          {
            brandId: 'stick',
            brandLabel: 'Stick',
            socials: [
              { platform: 'instagram', label: 'Instagram', url: STICK_URLS[0] },
              { platform: 'facebook', label: 'Facebook', url: STICK_URLS[1] },
              { platform: 'youtube', label: 'YouTube', url: STICK_URLS[2] },
              { platform: 'tiktok', label: 'TikTok', url: STICK_URLS[3] },
              { platform: 'google', label: 'Google', url: STICK_URLS[4] },
            ],
          },
        ],
      }),
    )
    for (const url of STICK_URLS) {
      expect(html).toContain(`href="${url}"`)
    }
    expect(html.match(/target="_blank"/g)?.length).toBe(5)
  })
})
