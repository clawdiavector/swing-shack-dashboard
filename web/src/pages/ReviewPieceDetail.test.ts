import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { InboxItem } from '../lib/api'
import { ReviewPieceDetail } from './ReviewPieceDetail'

const baseItem: InboxItem = {
  id: 'draft_asset:camp:asset1',
  type: 'draft_asset',
  brand_id: 'swing-shack',
  meta: {},
}

const noop = () => {}

function renderDetail(overrides: Partial<Parameters<typeof ReviewPieceDetail>[0]> = {}) {
  return renderToStaticMarkup(
    ReviewPieceDetail({
      item: baseItem,
      caption: 'Hello caption',
      visualUrl: 'https://cdn.example/x.png',
      visualBrief: '',
      imgBroken: false,
      asset: null,
      assetLoading: false,
      editingCaption: false,
      captionDraft: '',
      captionSaving: false,
      drafting: false,
      regenerateDisabled: false,
      regenerateTip: 'Queue a new draft image',
      onStartEditCaption: noop,
      onCancelEditCaption: noop,
      onCaptionDraftChange: noop,
      onSaveCaption: noop,
      onRegenerate: noop,
      onImgBroken: noop,
      ...overrides,
    }),
  )
}

describe('ReviewPieceDetail', () => {
  it('shows Edit caption and Regenerate controls', () => {
    const html = renderDetail()
    expect(html).toContain('Edit caption')
    expect(html).toContain('Regenerate')
    expect(html).toContain('data-testid="edit-caption-btn"')
    expect(html).toContain('data-testid="regenerate-btn"')
  })

  it('shows inline editor and Save when editing', () => {
    const html = renderDetail({ editingCaption: true, captionDraft: 'Draft text' })
    expect(html).toContain('data-testid="caption-editor"')
    expect(html).toContain('data-testid="save-caption-btn"')
    expect(html).toContain('Draft text')
    expect(html).not.toContain('data-testid="edit-caption-btn"')
  })

  it('disables Regenerate with cap tooltip when at_cap', () => {
    const tip = 'Daily image cap reached for swing-shack'
    const html = renderDetail({
      regenerateDisabled: true,
      regenerateTip: tip,
    })
    expect(html).toContain('disabled')
    expect(html).toContain(`title="${tip}"`)
  })

  it('shows Drafting label while queue pending', () => {
    const html = renderDetail({ drafting: true })
    expect(html).toContain('Drafting')
    expect(html).not.toContain('>Regenerate<')
  })
})
