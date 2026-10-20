import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AdsNextView } from './AdsNext'
import { DateView, dateInDays, type DateState } from './AdsDecisionDate'

const handlers = { onPreview: () => {}, onConfirm: () => {}, onCancel: () => {}, onUndo: () => {}, onDate: () => {} }
const html = (state: DateState) =>
  renderToStaticMarkup(<DateView adName="Putter ad" date="2026-11-03" state={state} handlers={handlers} />)

describe('DateView', () => {
  it('offers a date and a button, and sends nothing yet', () => {
    const out = html({ step: 'idle' })
    expect(out).toContain('value="2026-11-03"')
    expect(out).toContain('Set decision date')
  })
  it('says what will happen before it happens', () => {
    const out = html({
      step: 'confirm',
      preview: {
        adset_name: 'Putter Traffic',
        end_date: '2026-11-03',
        note: 'The ad set stops delivering at the end of that day.',
        ticket: 't',
      },
    })
    expect(out).toContain('Putter Traffic')
    expect(out).toContain('2026-11-03')
    expect(out).toContain('stops delivering')
    expect(out).toContain('Yes, set it')
  })
  it('offers undo once set', () => {
    expect(html({ step: 'set', actionId: 'a', endDate: '2026-11-03' })).toContain('Undo')
  })
  it('defaults to two weeks ahead', () => {
    expect(dateInDays(14, new Date('2026-10-20T10:00:00Z'))).toBe('2026-11-03')
  })
})

describe('AdsNextView decision date', () => {
  const brief = {
    top_actions: [{ rule: 'spend_mix', action: 'Move budget.' }],
    open: [
      {
        rule: 'open_ended_non_lead',
        status: 'DECISION_DATE',
        action: 'Set a decision date.',
        ad_id: '555',
        ad_name: 'Putter ad',
      },
    ],
  }
  it('lists other open items and shows the control only when changes are on', () => {
    const off = renderToStaticMarkup(<AdsNextView brief={brief as never} brandId="stick" canChange={false} />)
    expect(off).toContain('More open items (1)')
    expect(off).not.toContain('Set decision date')
    const on = renderToStaticMarkup(<AdsNextView brief={brief as never} brandId="stick" canChange />)
    expect(on).toContain('Set decision date')
  })
})
