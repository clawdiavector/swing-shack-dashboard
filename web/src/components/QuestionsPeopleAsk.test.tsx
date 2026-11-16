import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { QuestionsPeopleAsk } from './QuestionsPeopleAsk'

const questions = Array.from({ length: 15 }, (_, i) => ({
  question: `Question number ${i + 1}?`,
  from: i < 4 ? 'is club fitting worth it' : 'what is loft and lie',
}))

const base = {
  parkLabel: '20 November 2026',
  busyTitle: null as string | null,
  onPark: () => {},
}

describe('QuestionsPeopleAsk', () => {
  it('shows the first ten questions, each with a park button', () => {
    const html = renderToStaticMarkup(<QuestionsPeopleAsk {...base} questions={questions} />)
    expect(html).toContain('Questions people ask Google')
    expect(html).toContain('Question number 1?')
    expect(html).toContain('Question number 10?')
    expect(html).not.toContain('Question number 11?')
    expect(html).toContain('Show all 15')
    expect(html.match(/Park on 20 November 2026/g)?.length).toBe(10)
  })

  it('says what was searched', () => {
    const html = renderToStaticMarkup(<QuestionsPeopleAsk {...base} questions={questions} />)
    expect(html).toContain('is club fitting worth it')
  })

  it('says plainly when Google could not be read', () => {
    const html = renderToStaticMarkup(
      <QuestionsPeopleAsk {...base} questions={[]} error="Google suggestions could not be read" />,
    )
    expect(html).toContain('could not be read')
  })

  it('says when it is still loading', () => {
    const html = renderToStaticMarkup(<QuestionsPeopleAsk {...base} questions={null} />)
    expect(html).toContain('Looking up questions')
  })
})
