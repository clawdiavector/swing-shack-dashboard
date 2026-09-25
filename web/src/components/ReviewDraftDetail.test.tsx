import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { InboxItem } from '../lib/api'
import { ReviewDraftDetail, type ReviewDraftDetailProps } from './ReviewDraftDetail'

const fixtureItem: InboxItem = {
  id: 'draft_asset:camp:asset1',
  type: 'draft_asset',
  brand_id: 'swing-shack',
  title: 'Summer drop',
  meta: {
    caption: 'Headline here\nBody',
    primary_channel: 'instagram',
    composed: { instagram: '/brand-images/x.png', gbp: '/brand-images/y.png' },
    photo_candidates: [
      { index: 0, url: '/brand-images/a.png' },
      { index: 1, url: '/brand-images/b.png' },
    ],
    qc: { verdict: 'pass', selected: 0, scores: { layout: 0.9 }, reasons: [] },
    brief: { sections: ['Scene: rooftop', 'Mood: warm'] },
    reference_used: { url: '/brand-images/ref.png', selected_because: 'Top IG performer' },
  },
}

const noop = () => {}

function renderDetail(overrides: Partial<ReviewDraftDetailProps> = {}) {
  return renderToStaticMarkup(
    <ReviewDraftDetail
      item={fixtureItem}
      showBrandChip
      atImageCap={false}
      regenerateTip="Queue regenerate"
      busy={false}
      onApprove={noop}
      onReject={noop}
      onRegenerate={noop}
      onRecomposeHeadline={noop}
      onSwapCandidate={noop}
      {...overrides}
    />,
  )
}

describe('ReviewDraftDetail', () => {
  it('renders composed preview, channel tabs, and QC badge', () => {
    const html = renderDetail()
    expect(html).toContain('data-testid="review-draft-detail"')
    expect(html).toContain('data-testid="composed-preview"')
    expect(html).toContain('data-testid="channel-tab-instagram"')
    expect(html).toContain('data-testid="qc-badge"')
    expect(html).toContain('font-display')
  })

  it('shows candidate thumbs and swap control', () => {
    const html = renderDetail()
    expect(html).toContain('h-20 w-20')
    expect(html).toContain('data-testid="swap-candidate-1"')
  })

  it('disables regenerate at cap with tooltip', () => {
    const tip = 'Daily image cap reached for swing-shack'
    const html = renderDetail({ atImageCap: true, regenerateTip: tip })
    expect(html).toContain('data-testid="draft-regenerate-btn"')
    expect(html).toContain('disabled')
    expect(html).toContain(`title="${tip}"`)
    expect(html).toContain('data-testid="regenerate-cap-hint"')
  })

  it('exposes action row controls', () => {
    const html = renderDetail()
    expect(html).toContain('data-testid="draft-approve-btn"')
    expect(html).toContain('data-testid="draft-edit-headline-btn"')
    expect(html).toContain('data-testid="draft-reject-btn"')
  })
})
