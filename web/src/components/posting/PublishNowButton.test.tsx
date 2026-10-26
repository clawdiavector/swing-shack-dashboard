import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PublishNowButton } from './PublishNowButton'

const at1400 = new Date(2026, 9, 23, 14, 0, 0)

describe('PublishNowButton', () => {
  it('shows the +5 send time on the control before the click', () => {
    const html = renderToStaticMarkup(
      <PublishNowButton disabled={false} onClick={() => {}} now={at1400} />,
    )
    expect(html).toContain('Publish now')
    expect(html).toContain('Goes out at 14:05 (5 minutes from now).')
  })
})
