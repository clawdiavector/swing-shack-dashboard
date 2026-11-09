// Stick has its own Reach and Instagram data since PR #342 (6 Nov 2026), so Reach and
// What worked lately must ask for the selected brand instead of blocking everyone but
// Swing Shack.
import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../components/BrandSwitch', () => ({
  useBrand: () => ({ brandId: 'stick', brandLabel: 'Stick' }),
}))

import { ReachPage, reachRequests } from './ReachPage'
import { WorkedLately } from '../components/WorkedLately'

describe('Results for Stick', () => {
  it('Reach no longer says it is Swing Shack only', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ReachPage />
      </MemoryRouter>,
    )
    expect(html).not.toContain('only tracked for Swing Shack')
  })

  it('What worked lately no longer says it is Swing Shack only', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <WorkedLately />
      </MemoryRouter>,
    )
    expect(html).not.toContain('only tracked for Swing Shack')
  })

  it('Reach asks for the selected brand', () => {
    expect(reachRequests('stick')).toEqual([
      '/api/intel/performance?brand=stick',
      '/api/intel/explain?brand=stick',
    ])
  })
})
