import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { fillStarter } from './Moments'
import { MomentsTodayView } from './MomentsToday'

const item = (over: Record<string, unknown>) => ({
  title: 'T',
  source: 'IOL Sport',
  category: 'golf',
  act_today: false,
  age_hours: 2,
  why: 'Why.',
  starter_line: 'Line. {brand}.',
  ...over,
})

const html = (data: Parameters<typeof MomentsTodayView>[0]['data'], brandLabel?: string) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <MomentsTodayView data={data} brandLabel={brandLabel} />
    </MemoryRouter>,
  )

describe('MomentsTodayView', () => {
  it('shows nothing on a quiet day', () => {
    expect(html({ live: [item({})], upcoming: [] })).toBe('')
    expect(html({})).toBe('')
  })
  it('shows only act-today items, at most three, with a link to the full page', () => {
    const live = [1, 2, 3, 4].map((n) => item({ title: `Hot ${n}`, act_today: true }))
    const out = html({ live: [item({ title: 'Cold' }), ...live] }, 'Stick')
    expect(out).toContain('Hot 1')
    expect(out).toContain('Hot 3')
    expect(out).not.toContain('Hot 4')
    expect(out).not.toContain('Cold')
    expect(out).toContain('href="/results/trends"')
    expect(out).toContain('Line. Stick.')
  })
  it('flags dates that need preparing now', () => {
    const out = html({
      upcoming: [
        { date: '2026-10-31', title: 'Halloween', days_to: 11, prep_by: '2026-10-24', status: 'prepare now' },
        { date: '2026-11-27', title: 'Black Friday', days_to: 38, prep_by: '2026-11-13', status: 'coming' },
      ],
    })
    expect(out).toContain('Halloween')
    expect(out).toContain('Prepare it now')
    expect(out).not.toContain('Black Friday')
  })
})

describe('fillStarter', () => {
  it('drops the sign-off when no brand is picked', () => {
    expect(fillStarter('Get low. {brand}.')).toBe('Get low.')
    expect(fillStarter('Get low. {brand}.', 'Swing Shack')).toBe('Get low. Swing Shack.')
  })
})
