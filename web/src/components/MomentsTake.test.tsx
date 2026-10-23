import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Take } from './Moments'

const base = {
  title: 'Air Force flyover',
  source: 'IOL',
  category: 'flyover',
  act_today: true,
  why: 'Low and loud.',
  starter_line: 'Get your score as low as that flyover. {brand}.',
}
const drafted = {
  ...base,
  angle: 'Everyone looked up.',
  lines: { 'swing-shack': 'Lower than our handicap. Almost.', stick: 'Low and steady, like a good swing.' },
}
const html = (item: typeof drafted | typeof base, brandId?: string, brandLabel?: string) =>
  renderToStaticMarkup(<Take item={item} brandId={brandId} brandLabel={brandLabel} />)

describe('Take', () => {
  it('shows the drafted take and the line for the brand in view', () => {
    const out = html(drafted, 'stick', 'Stick')
    expect(out).toContain('Everyone looked up.')
    expect(out).toContain('Low and steady')
    expect(out).not.toContain('Lower than our handicap')
    expect(out).toContain('edit before use')
  })
  it('shows each brand line, named, when no brand is picked', () => {
    const out = html(drafted)
    expect(out).toContain('Swing Shack: ')
    expect(out).toContain('Stick: ')
  })
  it('falls back to the template when nothing was drafted', () => {
    const out = html(base, 'stick', 'Stick')
    expect(out).toContain('Low and loud.')
    expect(out).toContain('as low as that flyover. Stick.')
  })
  it('does not offer a joke on a story marked not to joke about', () => {
    const out = html({ ...base, skip_joke: true } as typeof base, 'stick', 'Stick')
    expect(out).toContain('Not one to joke about')
    expect(out).not.toContain('Starter line')
  })
})
