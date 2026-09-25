import { expect, test } from '@playwright/test'

const draftItem = {
  id: 'draft_asset:camp-stick:asset-main',
  type: 'draft_asset',
  brand_id: 'stick',
  title: 'Rooftop moment',
  summary: 'Headline line',
  created_at: '2026-09-25T10:00:00Z',
  status: 'pending',
  meta: {
    campaign_id: 'camp-stick',
    asset_id: 'asset-main',
    primary_channel: 'instagram',
    caption: 'Headline line\nBody\nCTA',
    composed: {
      instagram: '/brand-images/ig-composed.png',
      gbp: '/brand-images/gbp-composed.png',
    },
    photo_candidates: [
      { index: 0, url: '/brand-images/a.png' },
      { index: 1, url: '/brand-images/b.png' },
    ],
    qc: { verdict: 'pass', selected: 0, scores: { layout: 0.92 }, reasons: [] },
    brief: { sections: ['Scene: rooftop bar', 'Lighting: golden hour'] },
    reference_used: { url: '/brand-images/ref.png', selected_because: 'Matched top IG post' },
  },
}

function jsonRoute(body: unknown, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(body) }
}

test.describe('Review draft v2', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/brands**', async (route) => {
      await route.fulfill(
        jsonRoute({
          brands: {
            stick: { id: 'stick', name: 'Stick', order: 1 },
            'swing-shack': { id: 'swing-shack', name: 'Swing Shack', order: 0 },
          },
        }),
      )
    })

    await page.route('**/api/inbox/unified**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      await route.fulfill(
        jsonRoute({
          ok: true,
          items: [draftItem],
          counts: { pending: 1, stale: 0, approved_today: 0 },
        }),
      )
    })

    await page.route('**/api/ops/images-today/**', async (route) => {
      await route.fulfill(jsonRoute({ ok: true, brand_id: 'stick', images_today: 0, cap: 2, at_cap: false }))
    })

    await page.goto('/app/review')
    await expect(page.getByTestId('review-draft-detail')).toBeVisible({ timeout: 15_000 })
  })

  test('approve posts to unified approve', async ({ page }) => {
    let approveHit = false
    await page.route('**/api/inbox/unified/**/approve', async (route) => {
      approveHit = true
      await route.fulfill(jsonRoute({ ok: true }))
    })
    await page.getByTestId('draft-approve-btn').click()
    await expect.poll(() => approveHit).toBe(true)
  })

  test('regenerate posts to P4 regenerate route', async ({ page }) => {
    let regenBody: Record<string, unknown> | null = null
    await page.route('**/api/drafts/**/regenerate', async (route) => {
      regenBody = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill(jsonRoute({ ok: true, enqueued: ['draft_photo'] }))
    })
    await page.getByTestId('draft-regenerate-btn').click()
    await page.getByTestId('regenerate-note').fill('darker background')
    await page.getByTestId('regenerate-submit').click()
    await expect.poll(() => regenBody?.note).toBe('darker background')
  })

  test('reject without reason stays blocked', async ({ page }) => {
    let rejectHit = false
    await page.route('**/api/inbox/unified/**/reject', async (route) => {
      rejectHit = true
      await route.fulfill(jsonRoute({ ok: true }))
    })
    await page.getByTestId('draft-reject-btn').click()
    await page.getByTestId('reject-submit').click()
    await expect(page.getByTestId('reject-reason-error')).toBeVisible()
    expect(rejectHit).toBe(false)
  })
})
