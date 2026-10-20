import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { BudgetView, rand, type BudgetEval } from './AdsBudget'

const base: BudgetEval = {
  budget: 8000,
  mtd_spend: 2000,
  projected_total: 7600,
  worst_case_total: 9100,
  left: 6000,
  safe_per_day: 545,
  daily_run_rate: 460,
  used_pct: 25,
  status: 'WATCH',
  headline: 'Fits on paper (R7,600), but Meta may spend up to a quarter more on a day: worst case R9,100.',
  complete: true,
}
// en-ZA puts a (narrow) no-break space between thousands; compare with plain spaces.
const plain = (s: string) => s.replace(/[  ]/g, ' ')
const html = (ev: BudgetEval | null, over: Partial<{ error: string | null }> = {}) =>
  plain(
    renderToStaticMarkup(
      <BudgetView ev={ev} input="8000" saving={false} error={over.error ?? null} onInput={() => {}} onSave={() => {}} />,
    ),
  )

describe('BudgetView', () => {
  it('shows where the month stands and the safe daily amount', () => {
    const out = html(base)
    expect(out).toContain('Watch')
    expect(out).toContain('R2 000')
    expect(out).toContain('R7 600')
    expect(out).toContain('R545')
    expect(out).toContain('Saving a budget changes nothing in Meta')
  })
  it('says so plainly when it is over', () => {
    const out = html({ ...base, status: 'OVER', left: -500, headline: 'The month budget is already spent.' })
    expect(out).toContain('Over budget')
  })
  it('invites a budget when none is set and none has been read yet', () => {
    expect(html(null)).toContain('first reading')
    expect(html({ ...base, budget: null, status: 'NO_BUDGET', left: null, safe_per_day: null })).toContain('No budget set')
  })
  it('warns when part of the spend could not be read', () => {
    expect(html({ ...base, complete: false })).toContain('could not be read')
  })
  it('formats rand', () => {
    expect(plain(rand(1234.6))).toBe('R1 235')
    expect(rand(null)).toBe('—')
  })
})
