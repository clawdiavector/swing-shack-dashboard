import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MomentsView } from './Moments'

const data = {
  upcoming: [
    {
      date: '2026-10-31',
      title: 'Halloween',
      angle: 'Light and playful.',
      days_to: 11,
      prep_by: '2026-10-24',
      status: 'coming' as const,
    },
    { date: '2026-10-23', title: 'Soon', days_to: 3, prep_by: '2026-10-16', status: 'prepare now' as const },
  ],
  live: [
    {
      title: 'Air Force flyover thrills the crowd',
      source: 'IOL Sport',
      category: 'flyover',
      act_today: true,
      age_hours: 2,
      why: 'Low and loud.',
      starter_line: 'Get your score as low as that flyover. {brand}.',
      link: 'https://example.com/a',
    },
  ],
  hidden_sensitive: 2,
}

describe('MomentsView', () => {
  it('shows dates to prepare for and how soon', () => {
    const html = renderToStaticMarkup(<MomentsView data={data} brandLabel="Stick" />)
    expect(html).toContain('Halloween')
    expect(html).toContain('prepare now')
    expect(html).toContain('prepare by')
  })
  it('puts the brand in the starter line and marks it as a template', () => {
    const html = renderToStaticMarkup(<MomentsView data={data} brandLabel="Stick" />)
    expect(html).toContain('edit before use')
    expect(html).toContain('as low as that flyover. Stick.')
    expect(html).toContain('act today')
  })
  it('says how many sensitive headlines were hidden', () => {
    expect(renderToStaticMarkup(<MomentsView data={data} />)).toContain('2 headlines hidden')
  })
  it('handles an empty desk', () => {
    const html = renderToStaticMarkup(<MomentsView data={{}} />)
    expect(html).toContain('Nothing on the calendar')
    expect(html).toContain('Nothing with a golf or sport angle')
  })
})
