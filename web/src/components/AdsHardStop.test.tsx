import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { BudgetEval } from './AdsBudget'
import { HardStopView, type HardState, type HardStopInfo } from './AdsHardStop'

const budget = { budget: 1000 } as BudgetEval
const handlers = { onPreview: () => {}, onConfirm: () => {}, onCancel: () => {}, onOff: () => {} }
const plain = (s: string) => s.replace(/[  ]/g, ' ')
const html = (info: HardStopInfo, state: HardState = { step: 'idle' }, b: BudgetEval | null = budget) =>
  plain(renderToStaticMarkup(<HardStopView info={info} budget={b} state={state} handlers={handlers} />))

describe('HardStopView', () => {
  it('starts off, explains it, and offers to turn it on', () => {
    const out = html({ on: false })
    expect(out).toContain('OFF')
    expect(out).toContain('Turn hard stop on')
    expect(out).toContain('only warns')
  })
  it('cannot be turned on without a budget', () => {
    expect(html({ on: false }, { step: 'idle' }, null)).toContain('disabled')
  })
  it('says the limit and offers to turn it off when on', () => {
    const out = html({ on: true, cap: 3_569_106 })
    expect(out).toContain('ON')
    expect(out).toContain('R35 691')
    expect(out).toContain('Turn hard stop off')
  })
  it('warns plainly when turning it on would stop everything now', () => {
    const out = html(
      { on: false },
      {
        step: 'confirm',
        preview: {
          plan: { action: 'set', cap: 1, stops_now: true, room: 1 },
          budget: 1000,
          mtd_spend: 2230,
          amount_spent: 3_492_103,
          current_cap: 0,
        },
      },
    )
    expect(out).toContain('every ad in this account would stop delivering right away')
    expect(out).toContain('Yes, turn it on')
  })
  it('shows the reason and no confirm button when blocked', () => {
    const out = html(
      { on: false },
      {
        step: 'confirm',
        preview: { plan: { action: 'blocked', reason: 'The account already has a spending limit.' }, budget: 1, mtd_spend: 0, amount_spent: 0, current_cap: 5 },
      },
    )
    expect(out).toContain('already has a spending limit')
    expect(out).not.toContain('Yes, turn it on')
  })
})
