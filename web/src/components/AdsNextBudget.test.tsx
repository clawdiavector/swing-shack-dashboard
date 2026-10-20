import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AdsNextView } from './AdsNext'

const brief = {
  top_actions: [{ rule: 'spend_mix', action: 'Move budget from traffic and awareness to the lead ads.' }],
  open: [
    { rule: 'best_lead_ad', status: 'SCALE', action: 'Raise this ad budget in steps of about 20%.', ad_id: '555', ad_name: '50+km Paarl' },
  ],
}

describe('AdsNextView budget approvals', () => {
  it('offers the budget change only when one-click changes are on', () => {
    const off = renderToStaticMarkup(<AdsNextView brief={brief as never} brandId="stick" canChange={false} />)
    expect(off).not.toContain('Raise budget by 20%')
    const on = renderToStaticMarkup(<AdsNextView brief={brief as never} brandId="stick" canChange />)
    expect(on).toContain('Raise budget by 20%')
  })
  it('puts a list of ad sets under the move-budget item', () => {
    const on = renderToStaticMarkup(<AdsNextView brief={brief as never} brandId="stick" canChange />)
    expect(on).toContain('Loading ad sets')
  })
})
