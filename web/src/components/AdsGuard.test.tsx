import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { GuardView, type GuardInfo, type GuardState } from './AdsGuard'

const handlers = { onPreview: () => {}, onConfirm: () => {}, onCancel: () => {}, onOff: () => {}, onUndo: () => {} }
const plain = (s: string) => s.replace(/[  ]/g, ' ')
const html = (info: GuardInfo, state: GuardState = { step: 'idle' }, hasBudget = true) =>
  plain(renderToStaticMarkup(<GuardView info={info} hasBudget={hasBudget} state={state} handlers={handlers} />))

const off: GuardInfo = { auto_pause: false, paused: [] }

describe('GuardView', () => {
  it('starts off, explains it and offers to turn it on', () => {
    const out = html(off)
    expect(out).toContain('OFF')
    expect(out).toContain('Turn budget guard on')
    expect(out).toContain('only warns')
  })
  it('cannot be turned on without a budget', () => {
    expect(html(off, { step: 'idle' }, false)).toContain('disabled')
  })
  it('shows the last check as a dry run when off', () => {
    const out = html({
      ...off,
      last: {
        at: '2026-10-20T11:05:00+00:00',
        plan: { trigger: true, reason: 'The month’s budget of R1,500 is used up (R2,387 spent).', targets: [{ id: '1' }, { id: '2' }], running: 2 },
      },
    })
    expect(out).toContain('With the guard on it would pause 2 ad sets')
  })
  it('lists exactly what would be paused before it is switched on', () => {
    const out = html(off, {
      step: 'confirm',
      preview: {
        budget: 1500,
        mtd_spend: 2387,
        plan: {
          trigger: true,
          reason: 'Used up.',
          running: 2,
          targets: [
            { id: '1', name: 'Dave Shafts traffic', campaign: '1000Questions' },
            { id: '2', name: 'Local Golfers', campaign: 'Fit Fact leads' },
          ],
        },
      },
    })
    expect(out).toContain('would pause 2 ad sets')
    expect(out).toContain('Dave Shafts traffic')
    expect(out).toContain('Yes, turn it on')
  })
  it('lists what it paused with a way back', () => {
    const out = html({ auto_pause: true, paused: [{ id: 'a', ad_id: '1', ad_name: 'Local Golfers', at: '2026-10-20T11:05:00+00:00', kind: 'pause_adset' }] })
    expect(out).toContain('ON')
    expect(out).toContain('Paused by the guard')
    expect(out).toContain('Turn back on')
    expect(out).toContain('Turn budget guard off')
  })
})
