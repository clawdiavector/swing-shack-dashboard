import { describe, expect, it } from 'vitest'
import { createMemoryRouter } from 'react-router'
import { PHOTO_QUERY, TODAY_PATH, backTarget, mondayOfIso } from './backNav'
import { persistedQuerySearch } from './queryState'

function searchOf(router: ReturnType<typeof createMemoryRouter>) {
  return new URLSearchParams(router.state.location.search)
}

/** Same decision the header button makes: history when there is some, otherwise Today. */
async function pressBack(router: ReturnType<typeof createMemoryRouter>, idx: number) {
  const target = backTarget({ idx })
  if (target == null) {
    await router.navigate(-1)
    return
  }
  await router.navigate({
    pathname: target,
    search: persistedQuerySearch(router.state.location.search),
  })
}

const routes = [
  { path: '/daily' },
  { path: '/calendar/lanes' },
  { path: '/review' },
  { path: '/review/:id' },
  { path: '/photos' },
]

describe('header Back paths', () => {
  it('calendar → post → Back lands on the same week, filter, and brand', async () => {
    const week = mondayOfIso('2026-11-02')
    const router = createMemoryRouter(routes, {
      initialEntries: [`/calendar/lanes?tab=month&month=2026-11&week=${week}&filter=fitting&brand=stick`],
    })
    await router.navigate('/review/post-1?brand=stick')
    await pressBack(router, 1)
    expect(router.state.location.pathname).toBe('/calendar/lanes')
    const q = searchOf(router)
    expect(q.get('week')).toBe(week)
    expect(q.get('filter')).toBe('fitting')
    expect(q.get('brand')).toBe('stick')
    expect(q.get('month')).toBe('2026-11')
  })

  it('Review → draft → Back returns to the same filter and brand', async () => {
    const router = createMemoryRouter(routes, {
      initialEntries: ['/review?filter=no-brief&brand=swing-shack'],
    })
    await router.navigate('/review/draft-9?brand=swing-shack')
    await pressBack(router, 1)
    expect(router.state.location.pathname).toBe('/review')
    const q = searchOf(router)
    expect(q.get('filter')).toBe('no-brief')
    expect(q.get('brand')).toBe('swing-shack')
  })

  it('Photos → photo → Back returns to the same filter and brand', async () => {
    const router = createMemoryRouter(routes, {
      initialEntries: ['/photos?filter=approved&brand=stick'],
    })
    await router.navigate(`/photos?filter=approved&brand=stick&${PHOTO_QUERY}=hero.jpg`)
    await pressBack(router, 1)
    expect(router.state.location.pathname).toBe('/photos')
    const q = searchOf(router)
    expect(q.get('filter')).toBe('approved')
    expect(q.get('brand')).toBe('stick')
    expect(q.get(PHOTO_QUERY)).toBeNull()
  })

  it('a page opened directly goes to Today', async () => {
    const router = createMemoryRouter(routes, {
      initialEntries: ['/review/draft-9?brand=stick'],
    })
    expect(backTarget({ idx: 0 })).toBe(TODAY_PATH)
    await pressBack(router, 0)
    expect(router.state.location.pathname).toBe('/daily')
  })
})
