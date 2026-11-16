import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { PlanPanel } from './PlanPanel'
import type { Plan } from '../../../lib/plan'

const { plan } = vi.hoisted(() => ({
  plan: {
  plan_id: 'pln-cat-test',
  brand_id: 'stick',
  brief_id: 'brf-cat',
  event_name: 'Black Friday',
  event_date: '2026-12-05',
  status: 'proposed',
  profile_label: 'Retail push',
  profile_reason: 'Because',
  items: [
    {
      item_id: 'itm-post-1',
      kind: 'post',
      title: 'Main post',
      due: '2026-12-05',
      days_before_event: 0,
      channel: 'Instagram',
      owner: 'marketing',
      note: '',
      needs_real_video: false,
      late: false,
      status: 'kept',
      source: 'template',
    },
  ],
  } as Plan,
}))

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react')
  let stateCall = 0
  return {
    ...actual,
    useState: <T,>(init: T | (() => T)) => {
      stateCall += 1
      if (stateCall === 1) return [plan, () => undefined] as const
      if (stateCall === 2) return [false, () => undefined] as const
      return actual.useState(init)
    },
    useEffect: () => undefined,
    useCallback: (fn: () => unknown) => fn,
  }
})

vi.mock('../../../lib/planMessages', () => ({
  defaultShots: () => [],
  shootRequest: () => '',
  shootSteps: () => [],
  signOffMessage: () => '',
  stepsWithoutShots: () => [],
}))

vi.mock('../../../lib/calendarAlerts', () => ({
  notifyAlertsChanged: () => undefined,
}))

vi.mock('../../../lib/api', () => ({
  archiveBrandItem: vi.fn(),
  previewBrandArchive: vi.fn(),
}))

vi.mock('../../../lib/plan', async () => {
  const actual = await vi.importActual<typeof import('../../../lib/plan')>('../../../lib/plan')
  return {
    ...actual,
    findPlan: vi.fn().mockResolvedValue({ ok: true, plan, found: true }),
    ensurePlanCatalog: vi.fn().mockResolvedValue({
      ok: true,
      pack_id: 'pack-cat-1',
      counts: { posts: 2, pictures: 0, pictures_yet: 2 },
    }),
  }
})

describe('PlanPanel catalog controls', () => {
  it('renders Open catalog and Copy link on a live plan', () => {
    const html = renderToStaticMarkup(<PlanPanel brandId="stick" briefId="brf-cat" />)
    expect(html).toContain('Open catalog')
    expect(html).toContain('Copy link')
    expect(html).toContain('data-testid="plan-catalog-open"')
    expect(html).toContain('data-testid="plan-catalog-copy"')
  })
})
