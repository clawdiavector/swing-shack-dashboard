import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Take } from './Moments'
import { deriveHeadline, StoryPackView } from './StoryPack'

const noop = () => {}
const view = (over: Partial<Parameters<typeof StoryPackView>[0]> = {}) =>
  renderToStaticMarkup(
    <StoryPackView
      open
      headline="Cardio for your thumbs"
      caption="Refreshing the live score every ball is just cardio for your thumbs."
      copied={null}
      onToggle={noop}
      onHeadline={noop}
      onCaption={noop}
      onCopy={noop}
      {...over}
    />,
  )

describe('deriveHeadline', () => {
  it('takes the first sentence when it fits', () => {
    expect(deriveHeadline('Cardio for your thumbs. Come hit a few.')).toBe('Cardio for your thumbs')
  })
  it('cuts a long first sentence at a word, within 40 characters', () => {
    const out = deriveHeadline('A US Open champ is heading to Sun City and you are still negotiating with your slice.')
    expect(out.length).toBeLessThanOrEqual(40)
    expect(out.endsWith(' ')).toBe(false)
    expect('A US Open champ is heading to Sun City and you are still negotiating with your slice.').toContain(out)
  })
})

describe('StoryPackView', () => {
  it('starts as a single button', () => {
    const out = view({ open: false })
    expect(out).toContain('Make a story')
    expect(out).not.toContain('Copy both')
  })
  it('offers the headline and caption to edit and copy, and says nothing is posted', () => {
    const out = view()
    expect(out).toContain('Cardio for your thumbs')
    expect(out).toContain('Copy headline')
    expect(out).toContain('Copy caption')
    expect(out).toContain('Copy both')
    expect(out).toContain('Nothing is saved or posted')
  })
  it('shows the character count and flags a headline over 40', () => {
    expect(view()).toContain('(22/40)')
    const long = view({ headline: 'x'.repeat(45) })
    expect(long).toContain('(45/40)')
    expect(long).toContain('text-red')
  })
  it('confirms a copy', () => {
    expect(view({ copied: 'both' })).toContain('Copied')
  })
})

describe('Take with the story button', () => {
  const item = {
    title: 'T',
    source: 'IOL',
    category: 'golf',
    act_today: true,
    why: 'Why.',
    starter_line: 'Line. {brand}.',
    lines: { stick: 'Pros play fitted clubs. The rest of us play Uncle’s old set.' },
    headlines: { stick: 'Fitted clubs, finally' },
  }
  it('puts the drafted headline in the story panel', () => {
    const out = renderToStaticMarkup(<Take item={item} brandId="stick" brandLabel="Stick" />)
    expect(out).toContain('Make a story')
  })
})
