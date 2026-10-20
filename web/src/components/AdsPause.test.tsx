import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AdsNextView } from './AdsNext'
import { PauseView, type PauseState } from './AdsPause'

const handlers = { onPreview: () => {}, onConfirm: () => {}, onCancel: () => {}, onUndo: () => {} }
const html = (state: PauseState) =>
  renderToStaticMarkup(<PauseView adName="Putter ad" state={state} handlers={handlers} />)

describe('PauseView', () => {
  it('starts with a single button and sends nothing', () => {
    expect(html({ step: 'idle' })).toContain('Pause this ad')
  })
  it('names the ad and asks before pausing', () => {
    const out = html({
      step: 'confirm',
      preview: { ad_id: '1', ad_name: 'Putter ad', status_now: 'ACTIVE', will_set: 'PAUSED', ticket: 't' },
    })
    expect(out).toContain('Putter ad')
    expect(out).toContain('Yes, pause it')
    expect(out).toContain('Cancel')
  })
  it('offers undo once paused', () => {
    expect(html({ step: 'paused', actionId: 'a' })).toContain('Undo')
  })
  it('shows the reason when refused', () => {
    expect(html({ step: 'error', message: 'The ad changed since you looked.' })).toContain('changed since')
  })
})

describe('AdsNextView pause buttons', () => {
  const brief = { top_actions: [{ action: 'Set a decision date.', ads: ['Putter ad'], ad_ids: ['555'] }] }
  it('hides them while one-click changes are off', () => {
    const out = renderToStaticMarkup(<AdsNextView brief={brief} brandId="stick" canChange={false} />)
    expect(out).not.toContain('Pause this ad')
  })
  it('shows one per ad when switched on', () => {
    const out = renderToStaticMarkup(<AdsNextView brief={brief} brandId="stick" canChange />)
    expect(out).toContain('Pause this ad')
  })
})
