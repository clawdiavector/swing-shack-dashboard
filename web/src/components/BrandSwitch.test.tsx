import './brandSwitchTestDom'
import { act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SCOPE_KEY } from '../lib/brands'
import { BrandProvider, BrandRefresh, BrandSwitch, useBrand, useBrandScope } from './BrandSwitch'

const BRANDS = {
  active_brand_id: 'swing-shack',
  default_brand_id: 'swing-shack',
  brands: {
    'swing-shack': { display_name: 'Swing Shack', active: true, order: 1 },
    stick: { display_name: 'Stick', active: true, order: 2 },
  },
}

/** Mount-only fetch stand-in. A brand switch must remount this, not just rerender it. */
const loads: string[] = []

function PageProbe() {
  const { brandId } = useBrand()
  const { scope, isAll } = useBrandScope()
  useEffect(() => {
    loads.push(`${isAll ? 'all' : scope}:${brandId ?? ''}`)
  }, [])
  return <p data-probe="page">{scope}</p>
}

function Desk() {
  return (
    <BrandProvider>
      <BrandSwitch />
      <BrandRefresh>
        <PageProbe />
      </BrandRefresh>
    </BrandProvider>
  )
}

describe('BrandSwitch refresh', () => {
  let root: Root
  let host: HTMLDivElement
  let active = 'swing-shack'

  beforeEach(() => {
    loads.length = 0
    active = 'swing-shack'
    localStorage.clear()
    host = document.createElement('div')
    document.body.appendChild(host)
    root = createRoot(host)
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        const path = String(url)
        if (path === '/api/brands') {
          return Response.json({ ...BRANDS, active_brand_id: active })
        }
        const select = path.match(/^\/api\/brands\/([^/]+)\/select$/)
        if (select && init?.method === 'POST') {
          active = decodeURIComponent(select[1])
          return Response.json({ ok: true, brand_id: active })
        }
        return new Response('missing', { status: 404 })
      }),
    )
  })

  afterEach(() => {
    act(() => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  async function render() {
    await act(async () => {
      root.render(<Desk />)
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }

  function button(): HTMLButtonElement {
    const found = host.querySelector('button')
    if (!found) throw new Error('brand switch button missing')
    return found
  }

  async function choose(label: string) {
    await act(async () => {
      button().click()
    })
    const option = [...host.querySelectorAll('[role="option"]')].find((el) => el.textContent?.includes(label))
    if (!option) throw new Error(`missing option ${label}`)
    await act(async () => {
      ;(option as HTMLButtonElement).click()
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }

  it('refetches the open page when the header brand changes', async () => {
    await render()
    expect(loads).toEqual(['all:'])
    expect(button().textContent).toContain('All brands')
    const settled = loads.length

    await choose('Stick')

    expect(loads).toHaveLength(settled + 1)
    expect(loads.at(-1)).toBe('stick:stick')
    expect(button().textContent).toContain('Stick')
    expect(localStorage.getItem(SCOPE_KEY)).toBe('stick')
    expect(active).toBe('stick')

    await choose('Swing Shack')

    expect(loads).toHaveLength(settled + 2)
    expect(loads.at(-1)).toBe('swing-shack:swing-shack')
    expect(button().textContent).toContain('Swing Shack')
  })

  it('refetches when the desk goes back to all brands', async () => {
    await render()
    await choose('Stick')
    const before = loads.length
    await choose('All brands')
    expect(loads).toHaveLength(before + 1)
    expect(loads.at(-1)).toBe('all:stick')
    expect(button().textContent).toContain('All brands')
    expect(localStorage.getItem(SCOPE_KEY)).toBe('all')
  })

  it('restores the picked brand after a reload', async () => {
    await render()
    await choose('Stick')
    await act(async () => root.unmount())

    loads.length = 0
    root = createRoot(host)
    await render()

    expect(button().textContent).toContain('Stick')
    expect(loads.at(-1)).toBe('stick:stick')
    expect(localStorage.getItem(SCOPE_KEY)).toBe('stick')
  })
})
