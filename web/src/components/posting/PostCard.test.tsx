import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { PostCard } from './PostCard'
import type { PostingWeekPost } from '../../lib/postingWeek'

const basePost: PostingWeekPost = {
  calendar_id: 'cal-1',
  title: 'Mystery promo',
  stages: { booked: true },
  state: 'gap',
  image_url: '/brand-images/stale-random.png',
  gap: {
    reason: 'no_layout',
    label: 'No layout for mystery',
    post_type: 'mystery',
  },
}

function renderCard(post: PostingWeekPost) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <PostCard post={post} dayDate="2026-10-12" weekday="Sun" />
    </MemoryRouter>,
  )
}

describe('PostCard gap state', () => {
  it('renders gap tile without img when state is gap', () => {
    const html = renderCard(basePost)
    expect(html).toContain('data-testid="gap-tile"')
    expect(html).toContain('No layout for mystery')
    expect(html).not.toMatch(/<img[\s>]/)
  })
})
