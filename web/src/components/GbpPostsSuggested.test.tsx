import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PostCard, type PostHandlers } from './GbpPosts'

const handlers: PostHandlers = {
  onApprove: () => {},
  onUnapprove: () => {},
  onPublish: () => {},
  onDelete: () => {},
  onPhoto: () => {},
  onSave: async () => true,
}
const draft = { id: 'a', title: 'Fit first', body: 'Custom club fitting.', cta: 'Book', link: 'https://stickgolf.co.za/', imageUrl: '/x.jpg' }
const html = (suggestedWhy?: string) =>
  renderToStaticMarkup(<PostCard d={draft} busy={false} terms={[]} handlers={handlers} suggestedWhy={suggestedWhy} />)

describe('PostCard suggestion', () => {
  it('flags the suggested post and says why', () => {
    const out = html('People searched “club fitting” 90 times on Google lately.')
    expect(out).toContain('Suggested to go out next.')
    expect(out).toContain('90 times')
  })
  it('shows nothing extra on other posts', () => {
    expect(html()).not.toContain('Suggested to go out next.')
  })
})
