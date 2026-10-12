import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ChannelPicker } from './ChannelPicker'

describe('ChannelPicker', () => {
  it('renders IG/FB/GBP toggles and coming-soon platforms disabled', () => {
    const html = renderToStaticMarkup(
      <ChannelPicker
        available={['instagram', 'facebook', 'gbp']}
        coming={['youtube', 'tiktok']}
        picked={['instagram', 'facebook']}
        onChange={() => {}}
      />,
    )
    expect(html).toContain('data-testid="channel-picker"')
    expect(html).toContain('data-testid="channel-picker-instagram"')
    expect(html).toContain('data-testid="channel-picker-facebook"')
    expect(html).toContain('data-testid="channel-picker-gbp"')
    expect(html).toContain('data-testid="channel-picker-youtube"')
    expect(html).toContain('Coming later')
    expect(html).toContain('disabled')
  })

  it('is read-only when locked', () => {
    const html = renderToStaticMarkup(
      <ChannelPicker
        available={['instagram', 'facebook']}
        picked={['instagram']}
        locked
      />,
    )
    expect(html).toContain('disabled')
  })

  it('shows empty hint when picked is empty and not locked', () => {
    const html = renderToStaticMarkup(
      <ChannelPicker available={['instagram', 'facebook']} picked={[]} onChange={vi.fn()} />,
    )
    expect(html).toContain('data-testid="channel-picker-empty"')
  })
})
