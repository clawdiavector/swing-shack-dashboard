import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AdsNextView } from './AdsNext'

describe('AdsNextView', () => {
  it('lists the top actions and the recommendation-only note', () => {
    const html = renderToStaticMarkup(
      <AdsNextView
        brief={{
          date: '2026-10-19',
          headline: { open: 10, new: 0, resolved: 0 },
          top_actions: [
            { action: 'Move budget to the lead ads.', why: '36% of spend made leads.', severity: 'medium', days_open: 11 },
          ],
        }}
      />,
    )
    expect(html).toContain('Move budget to the lead ads.')
    expect(html).toContain('36% of spend made leads.')
    expect(html).toContain('10 open')
    expect(html).toContain('Nothing here changes an ad')
    expect(html).toContain('href="/ads-brief"')
  })

  it('says so when nothing needs doing', () => {
    const html = renderToStaticMarkup(<AdsNextView brief={{ top_actions: [] }} />)
    expect(html).toContain('Nothing needs doing')
  })
})
