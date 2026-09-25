import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import {
  deleteBrandReference,
  postBrandReference,
  runSocialIngest,
} from '../lib/api'
import { toggleBrandReference } from '../lib/brandVisuals'
import { BrandVisualsLayout } from './BrandVisuals'

const mockPayload = {
  social: [
    {
      id: 'post1',
      platform: 'instagram',
      thumb_url: '/api/visual-library/stick/image/post1.jpg',
      caption: 'Hello world caption',
      posted_at: '2026-01-01T00:00:00Z',
      metrics: { likes: 12, comments: 3 },
      is_reference: false,
    },
  ],
  drive: [
    {
      id: 'hero-shot',
      folder: 'products',
      thumb_url: '/api/visual-library/stick/image/hero-shot.jpg',
      is_reference: false,
    },
  ],
  references: [
    {
      id: 'ref-abc',
      platform: 'instagram',
      pillar: 'demo',
      thumb_url: '/api/visual-library/stick/image/ref.jpg',
      label: 'Hero',
    },
  ],
}

describe('BrandVisualsLayout', () => {
  it('renders grids from mocked visuals payload', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <BrandVisualsLayout
          brandLabel="Stick"
          needBrand={false}
          platforms={['instagram', 'facebook']}
          platform="instagram"
          onPlatformChange={() => undefined}
          social={mockPayload.social}
          drive={mockPayload.drive}
          references={mockPayload.references}
          loading={false}
          ingestBusy={false}
          toggleBusyId={null}
          toast={null}
          onRunIngest={() => undefined}
          onToggleSocial={() => undefined}
          onToggleDrive={() => undefined}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('Hello world caption')
    expect(html).toContain('12 likes')
    expect(html).toContain('hero-shot')
    expect(html).toContain('Products')
    expect(html).toContain('demo')
  })

  it('shows empty state ingest control', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <BrandVisualsLayout
          brandLabel="Stick"
          needBrand={false}
          platforms={['instagram']}
          platform="instagram"
          onPlatformChange={() => undefined}
          social={[]}
          drive={[]}
          references={[]}
          loading={false}
          ingestBusy={false}
          toggleBusyId={null}
          toast={null}
          onRunIngest={() => undefined}
          onToggleSocial={() => undefined}
          onToggleDrive={() => undefined}
        />
      </MemoryRouter>,
    )
    expect(html).toContain('Run social ingest')
  })
})

describe('brand visuals API helpers', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it('toggle calls POST then DELETE', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, dna: {} }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, dna: {} }),
      })

    await postBrandReference('stick', { source: 'social', id: 'post1', platform: 'instagram' })
    await deleteBrandReference('stick', 'post1')
    await toggleBrandReference('stick', 'post2', false, 'drive')

    expect(fetchMock).toHaveBeenCalledTimes(3)
    const postCall = fetchMock.mock.calls[0]
    expect(postCall[0]).toBe('/api/brand/stick/references')
    expect(postCall[1]?.method).toBe('POST')
    const deleteCall = fetchMock.mock.calls[1]
    expect(deleteCall[0]).toBe('/api/brand/stick/references/post1')
    expect(deleteCall[1]?.method).toBe('DELETE')
    const togglePost = fetchMock.mock.calls[2]
    expect(togglePost[0]).toBe('/api/brand/stick/references')
    expect(togglePost[1]?.method).toBe('POST')
  })

  it('empty state button posts the job run', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, verdict: 'OK' }),
    })
    await runSocialIngest('stick')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/jobs/run/social_ingest?brand=stick',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
