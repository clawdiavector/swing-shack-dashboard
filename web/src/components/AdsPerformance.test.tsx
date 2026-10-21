import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PerformanceView, verdict, type PerformanceData } from './AdsPerformance'

const plain = (s: string) => s.replace(/[  ]/g, ' ')
const perf = (o: object = {}) => ({
  impressions: 5000, leads: 0, messages: 0, cost_per_lead: null, cost_per_message: null, cost_per_session: 2,
  engaged_pct: 25, click_to_session_pct: 90, key_events: 0, ...o,
})
const row = (o: object = {}) =>
  ({ ad_id: '1', ad_name: 'fitting_video_v1', campaign: 'ss_traffic_fitting_sep26', destination: 'WEBSITE', spend: 200, link_clicks: 100, ga_sessions: 100, ga_key_events: 0, perf: perf(), ...o }) as never

const data = (ads: object[]): PerformanceData =>
  ({
    summary: {} as never,
    errors: [],
    ads: ads as never,
    totals: { spend: 440, leads: 8, messages: 0, cost_per_lead: 30, ga_sessions: 100, ga_engaged_pct: 25, ga_key_events: 0, cost_per_session: 2 },
  }) as PerformanceData

describe('verdict', () => {
  it('flags a page that does not hold visitors', () => {
    expect(verdict(row(), null)?.text).toContain('Only 25%')
  })
  it('praises a page that does', () => {
    expect(verdict(row({ perf: perf({ engaged_pct: 70 }) }), null)?.tone).toBe('green')
  })
  it('compares lead ads with the brand average, but only with enough leads', () => {
    const lead = (cpl: number, leads: number) => row({ destination: 'LEAD_FORM', ga_sessions: 0, perf: perf({ leads, cost_per_lead: cpl, cost_per_session: null, engaged_pct: null, key_events: null }) })
    expect(verdict(lead(25, 10), 30)?.tone).toBe('green')
    expect(verdict(lead(40, 10), 30)?.tone).toBe('red')
    expect(verdict(lead(10, 2), 30)).toBeNull()
  })
  it('says enquiry counting is new when visits are fine and none are recorded', () => {
    expect(verdict(row({ perf: perf({ engaged_pct: 40 }) }), null)?.text).toContain('Counting only started')
  })
  it('says nothing when there is nothing fair to say', () => {
    expect(verdict(row({ ga_sessions: 10, perf: perf({ engaged_pct: 40, key_events: 1 }) }), null)).toBeNull()
  })
})

describe('PerformanceView', () => {
  it('shows brand totals and one card per ad with spend, visits, engagement and enquiries', () => {
    const out = plain(renderToStaticMarkup(<PerformanceView t={data([row()])} />))
    expect(out).toContain('Spent R440 in 31 days')
    expect(out).toContain('8 leads at R30 each')
    expect(out).toContain('fitting_video_v1')
    expect(out).toContain('Visits (GA4)')
    expect(out).toContain('25%')
    expect(out).toContain('Only 25% of visitors stayed')
  })
  it('shows leads for a lead ad and no website numbers', () => {
    const lead = row({ destination: 'LEAD_FORM', perf: perf({ leads: 8, cost_per_lead: 30, cost_per_session: null, engaged_pct: null, key_events: null, click_to_session_pct: null }) })
    const out = plain(renderToStaticMarkup(<PerformanceView t={data([lead])} />))
    expect(out).toContain('Leads')
    expect(out).toContain('R30 each')
    expect(out).toContain('Lead form')
  })
  it('says so when no ad delivered', () => {
    expect(renderToStaticMarkup(<PerformanceView t={data([])} />)).toContain('No ad delivered')
  })
})
