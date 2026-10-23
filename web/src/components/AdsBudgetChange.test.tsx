import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ChangeView, MoveBudgetView, moveSuggestions, type ChangeState } from './AdsBudgetChange'

const handlers = { onPreview: () => {}, onConfirm: () => {}, onCancel: () => {}, onUndo: () => {} }
const plain = (s: string) => s.replace(/[  ]/g, ' ')
const html = (state: ChangeState) =>
  plain(renderToStaticMarkup(<ChangeView label="Raise budget by 20%" state={state} handlers={handlers} />))

const preview = (ctx: object = {}) => ({
  adset_name: 'Local Golfers',
  campaign: 'Fit Fact leads',
  before: 30,
  after: 36,
  change_pct: 20,
  per_day: 6,
  ticket: 't',
  context: ctx,
})

describe('ChangeView', () => {
  it('is one button until pressed, so nothing is sent', () => {
    expect(html({ step: 'idle' })).toContain('Raise budget by 20%')
  })
  it('shows exactly what changes and asks for approval', () => {
    const out = html({ step: 'confirm', preview: preview() })
    expect(out).toContain('Local Golfers')
    expect(out).toContain('R30')
    expect(out).toContain('R36')
    expect(out).toContain('+20%')
    expect(out).toContain('Approve change')
  })
  it('warns when raising a budget that is already over the month, and says what the guard will do', () => {
    const out = html({
      step: 'confirm',
      preview: preview({ month_status: 'OVER', budget: 1500, guard_on: true }),
    })
    expect(out).toContain('already over')
    expect(out).toContain('pause this ad set again')
  })
  it('offers undo once changed', () => {
    expect(html({ step: 'done', actionId: 'a', before: 30, after: 36 })).toContain('Undo')
  })
})

describe('move budget', () => {
  const sets = [
    { id: '1', name: 'Traffic set', kind: 'daily', amount: 37, level: 'adset', objective: 'OUTCOME_TRAFFIC' },
    { id: '2', name: 'Leads set', kind: 'daily', amount: 30, level: 'adset', objective: 'OUTCOME_LEADS' },
    { id: '3', name: 'Whole campaign', kind: 'daily', amount: 200, level: 'campaign', objective: 'OUTCOME_LEADS' },
    { id: '4', name: 'Lifetime set', kind: 'lifetime', amount: 500, level: 'adset', objective: 'OUTCOME_AWARENESS' },
  ]
  it('lowers traffic and awareness, raises leads and chats, and skips what cannot be changed here', () => {
    const s = moveSuggestions(sets)
    expect(s.map((x) => [x.row.id, x.pct])).toEqual([
      ['1', -0.5],
      ['2', 0.2],
    ])
  })
  it('renders a button per ad set', () => {
    const out = plain(renderToStaticMarkup(<MoveBudgetView brandId="stick" sets={sets} />))
    expect(out).toContain('Lower by half')
    expect(out).toContain('Raise by 20%')
    expect(out).not.toContain('Whole campaign')
  })
})
