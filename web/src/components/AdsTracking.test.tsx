import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TrackingView, type Tracking } from './AdsTracking'

const t: Tracking = {
  summary: {
    running_ads: 3,
    website_ads: 2,
    website_with_complete_utm: 1,
    website_with_problems: 1,
    never_reach_site: 1,
    unknown_destination: 0,
    ga_paid_sessions: 1500,
    ga_matched: 1400,
  },
  ads: [
    { ad_id: '1', ad_name: 'Putter ad', campaign: 'C1', destination: 'WEBSITE', host: 'shop.example', utm: {}, issues: [], notes: [], ga_sessions: 612, spend: 100, link_clicks: 700 },
    { ad_id: '2', ad_name: 'Walk ad', campaign: 'C2', destination: 'WEBSITE', host: 'shop.example', utm: {}, issues: ['PLACEHOLDER_LITERAL'], notes: ["Source 'x' differs from the proposed 'meta'."], ga_sessions: 0, spend: 50, link_clicks: 10 },
    { ad_id: '3', ad_name: 'Leads ad', campaign: 'C3', destination: 'LEAD_FORM', host: null, utm: {}, issues: [], notes: ['Never reaches the website: measured in Meta (leads, messages), not GA4.'], ga_sessions: 0, spend: 20, link_clicks: 5 },
  ],
  errors: [],
}

describe('TrackingView', () => {
  const out = renderToStaticMarkup(<TrackingView t={t} />)
  it('summarises the counts and what Google Analytics saw', () => {
    expect(out).toContain('3 running ads')
    expect(out).toContain('1500 paid sessions')
  })
  it('marks good and bad tags and explains the problem in plain words', () => {
    expect(out).toContain('Tags ok')
    expect(out).toContain('Fix tags')
    expect(out).toContain('placeholder was typed as text')
  })
  it('does not fault lead ads for having no UTMs', () => {
    expect(out).toContain('Lead form')
    expect(out).toContain('measured in Meta')
  })
})
