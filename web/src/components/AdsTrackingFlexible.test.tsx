import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TrackingView, type Tracking } from './AdsTracking'

const proposal = {
  ad_name: 'fitting_video_v1',
  adset_name: 'ss_traffic_fitting_sep26_set',
  campaign_name: 'ss_traffic_fitting_sep26',
  url_tags: 'utm_source=meta&utm_medium=paid_social&utm_campaign=c&utm_content=a&utm_id=1',
}
const t = (fixable: boolean): Tracking => ({
  summary: { running_ads: 1, website_ads: 1, website_with_complete_utm: 0, website_with_problems: 1, never_reach_site: 0, unknown_destination: 0, ga_paid_sessions: 1, ga_matched: 1 },
  ads: [
    {
      ad_id: '1', ad_name: 'x', campaign: 'c', destination: 'WEBSITE', host: 'h', utm: {}, issues: ['NO_UTM'], notes: [],
      ga_sessions: 1, spend: 1, link_clicks: 1, ids: { campaign: 'c1', adset: 's1' },
      names: { ad: 'fitting_video_v1', adset: 'ss_traffic_fitting_sep26_set', campaign: 'ss_traffic_fitting_sep26' },
      current_tags: '', proposal, tags_fixable: fixable,
    },
  ] as never,
  errors: [],
})

describe('flexible creative', () => {
  it('offers the tag button only when the tags can be fixed from here', () => {
    expect(renderToStaticMarkup(<TrackingView t={t(true)} brandId="stick" canChange />)).toContain('Add standard UTM tags')
    expect(renderToStaticMarkup(<TrackingView t={t(true)} brandId="stick" canChange />)).not.toContain('flexible creative')
  })
  it('says what to do instead when it cannot', () => {
    const out = renderToStaticMarkup(<TrackingView t={t(false)} brandId="stick" canChange />)
    expect(out).not.toContain('Add standard UTM tags')
    expect(out).toContain('flexible creative')
    expect(out).toContain('utm_id=1')
  })
})
