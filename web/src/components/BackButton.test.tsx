import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { BackButton } from './ui'

describe('BackButton', () => {
  it('is one Back control', () => {
    const html = renderToStaticMarkup(<BackButton onClick={() => undefined} />)
    expect(html.match(/aria-label="Back"/g)).toHaveLength(1)
    expect(html).toContain('>Back<')
  })
})
