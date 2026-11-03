import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { BudgetView, type BudgetEval } from './AdsBudget'

const week: BudgetEval = {
  period: 'week',
  budget: 1000,
  mtd_spend: 400,
  projected_total: 900,
  worst_case_total: 1100,
  left: 600,
  safe_per_day: 150,
  daily_run_rate: 100,
  status: 'OK',
  headline: 'On track: R900 expected of a R1,000 budget.',
  complete: false,
}
const plain = (s: string) => s.replace(/[  ]/g, ' ')
const html = (ev: BudgetEval | null, period: 'week' | 'month') =>
  plain(
    renderToStaticMarkup(
      <BudgetView ev={ev} input="1000" saving={false} error={null} onInput={() => {}} onSave={() => {}} period={period} onPeriod={() => {}} />,
    ),
  )

describe('BudgetView per week', () => {
  it('speaks of the week and lets you pick week or month', () => {
    const out = html(week, 'week')
    expect(out).toContain('Weekly budget (R)')
    expect(out).toContain('Expected by week end')
    expect(out).toContain('this week')
    expect(out).toContain('Per week')
    expect(out).toContain('Per month')
    expect(out).not.toContain('month end')
  })
  it('keeps month wording for a monthly budget', () => {
    const out = html({ ...week, period: 'month' }, 'month')
    expect(out).toContain('Monthly budget (R)')
    expect(out).toContain('Expected by month end')
  })
})
