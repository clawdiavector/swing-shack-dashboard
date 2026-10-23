import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ApproveView, type ApproveState } from './AdsApprove'
import { TrackingView, type Tracking } from './AdsTracking'

type P = { before: string; after: string; ticket: string }
const handlers = { onPreview: () => {}, onConfirm: () => {}, onCancel: () => {}, onUndo: () => {} }
const view = (state: ApproveState<P>, warning?: (p: P) => string | undefined) =>
  renderToStaticMarkup(
    <ApproveView<P>
      label="Rename ad"
      state={state}
      handlers={handlers}
      describe={(p) => <p>Rename {p.before} to {p.after}?</p>}
      doneText={(p) => `Renamed to ${p.after}.`}
      warning={warning}
    />,
  )
const pv: P = { before: 'Old ad', after: 'fitting_video_v1', ticket: 't' }

describe('ApproveView', () => {
  it('is a single button until pressed', () => {
    expect(view({ step: 'idle' })).toContain('Rename ad')
  })
  it('says exactly what changes and waits for approval', () => {
    const out = view({ step: 'confirm', preview: pv })
    expect(out).toContain('fitting_video_v1')
    expect(out).toContain('Approve change')
    expect(out).toContain('Cancel')
  })
  it('shows a warning when there is one', () => {
    expect(view({ step: 'confirm', preview: pv }, () => 'The ad goes back through review.')).toContain('goes back through review')
  })
  it('offers undo once done', () => {
    const out = view({ step: 'done', actionId: 'a', preview: pv })
    expect(out).toContain('Renamed to fitting_video_v1.')
    expect(out).toContain('Undo')
  })
})

const ad = (over: object = {}) => ({
  ad_id: '1',
  ad_name: 'New Traffic Ad',
  campaign: 'Putter Traffic',
  destination: 'WEBSITE' as const,
  host: 'shop.example',
  utm: {},
  issues: ['NO_UTM'],
  notes: [],
  ga_sessions: 5,
  spend: 10,
  link_clicks: 20,
  ids: { campaign: 'c1', adset: 's1' },
  names: { ad: 'New Traffic Ad', adset: 'New Traffic Ad set', campaign: 'Putter Traffic' },
  current_tags: '',
  proposal: {
    ad_name: 'fitting_video_v1',
    adset_name: 'ss_traffic_fitting_sep26_set',
    campaign_name: 'ss_traffic_fitting_sep26',
    url_tags: 'utm_source=meta&utm_medium=paid_social&utm_campaign=ss_traffic_fitting_sep26&utm_content=fitting_video_v1&utm_id=1',
  },
  ...over,
})
const t = (ads: object[]): Tracking => ({
  summary: { running_ads: 1, website_ads: 1, website_with_complete_utm: 0, website_with_problems: 1, never_reach_site: 0, unknown_destination: 0, ga_paid_sessions: 5, ga_matched: 5 },
  ads: ads as never,
  errors: [],
})

describe('TrackingView fixes', () => {
  it('offers renames and UTM tags only when one-click changes are on', () => {
    expect(renderToStaticMarkup(<TrackingView t={t([ad()])} brandId="stick" canChange={false} />)).not.toContain('Rename ad')
    const on = renderToStaticMarkup(<TrackingView t={t([ad()])} brandId="stick" canChange />)
    expect(on).toContain('Rename ad')
    expect(on).toContain('Rename ad set')
    expect(on).toContain('Rename campaign')
    expect(on).toContain('Add standard UTM tags')
    expect(on).toContain('fitting_video_v1')
  })
  it('says so when an ad already meets the standard', () => {
    const done = ad({
      names: { ad: 'fitting_video_v1', adset: 'ss_traffic_fitting_sep26_set', campaign: 'ss_traffic_fitting_sep26' },
      current_tags: 'utm_source=meta&utm_medium=paid_social&utm_campaign=ss_traffic_fitting_sep26&utm_content=fitting_video_v1&utm_id=1',
    })
    expect(renderToStaticMarkup(<TrackingView t={t([done])} brandId="stick" canChange />)).toContain('Named and tagged to the standard')
  })
  it('does not offer tags for lead and message ads', () => {
    const lead = ad({ destination: 'LEAD_FORM', issues: [] })
    expect(renderToStaticMarkup(<TrackingView t={t([lead])} brandId="stick" canChange />)).not.toContain('Add standard UTM tags')
  })
})
