import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CmoBrief } from '../lib/api'
import { CmoCard } from './CmoCard'

const brief: CmoBrief = {
  week: { current: '19 Oct → 25 Oct' },
  verdict: { headline: 'The ad budget is used up.', tone: 'act', lines: ['Visits fell 34%.'] },
  numbers: [{ label: 'Website visits', value: '607', vs: 'was 926 (-34%)', note: 'All channels, 7 days' }],
  decisions: [
    { decision: 'Decide the ad budget', recommendation: 'Restart lead ads only if a lead is worth it.', because: 'R1,000 used up.', confidence: 'medium' },
  ],
  working: ['Google search is steady.'],
  not_working: ['fitting_video_v1 kept 9.9%.'],
  risks: [],
  gaps: ['No targets are set.'],
  next_week: ['Herman: decide the ad budget.'],
}

describe('CmoCard', () => {
  it('leads with the verdict and the decisions, with who does what next', () => {
    const out = renderToStaticMarkup(<CmoCard cmo={brief} />)
    expect(out).toContain('Where to go')
    expect(out).toContain('The ad budget is used up.')
    expect(out).toContain('Website visits')
    expect(out).toContain('Recommendation')
    expect(out).toContain('Herman: decide the ad budget.')
    expect(out).toContain('No targets are set.')
  })
  it('renders nothing when the report has no brief', () => {
    expect(renderToStaticMarkup(<CmoCard cmo={null} />)).toBe('')
    expect(renderToStaticMarkup(<CmoCard cmo={undefined} />)).toBe('')
  })
  it('does not show empty lists', () => {
    const out = renderToStaticMarkup(<CmoCard cmo={{ ...brief, risks: [] }} />)
    expect(out).not.toContain('Risks')
  })
})
