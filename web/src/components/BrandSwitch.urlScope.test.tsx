import './brandSwitchTestDom'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BrandProvider, BrandSwitch } from './BrandSwitch'

const BRANDS = {
  default_brand_id: 'swing-shack',
  brands: {
    'swing-shack': { display_name: 'Swing Shack', active: true, order: 1 },
    stick: { display_name: 'Stick', active: true, order: 2 },
  },
}

let currentSearch = ''
let go: NavigateFunction | null = null

function UrlProbe() {
  currentSearch = useLocation().search
  go = useNavigate()
  return null
}

/** The sidebar Plan link opens the page with ?brand= already in the address. */
function Desk({ at }: { at: string }) {
  return (
    <MemoryRouter initialEntries={[at]}>
      <BrandProvider>
        <BrandSwitch />
        <UrlProbe />
      </BrandProvider>
    </MemoryRouter>
  )
}

describe('BrandSwitch with ?brand= in the address', () => {
  let root: Root
  let host: HTMLDivElement
  let active = 'swing-shack'
  let selects: string[] = []

  beforeEach(() => {
    active = 'swing-shack'
    selects = []
    currentSearch = ''
    go = null
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
          selects.push(active)
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

  async function settle() {
    for (let i = 0; i < 5; i++) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0))
      })
    }
  }

  async function render(at: string) {
    await act(async () => {
      root.render(<Desk at={at} />)
    })
    await settle()
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
    await settle()
  }

  it('keeps the picked brand when the address still names the old one', async () => {
    await render('/calendar/posts?brand=swing-shack')
    expect(button().textContent).toContain('Swing Shack')
    selects = []

    await choose('Stick')

    expect(button().textContent).toContain('Stick')
    expect(active).toBe('stick')
    expect(new URLSearchParams(currentSearch).get('brand')).toBe('stick')
    expect(selects).toEqual(['stick'])
  })

  it('still follows the address when a link changes ?brand=', async () => {
    await render('/calendar/posts?brand=swing-shack')
    expect(button().textContent).toContain('Swing Shack')

    await act(async () => {
      go?.('/calendar/posts?brand=stick')
    })
    await settle()

    expect(button().textContent).toContain('Stick')
    expect(active).toBe('stick')
  })
})
