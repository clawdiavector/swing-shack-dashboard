import { ChevronDown } from 'lucide-react'
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { fetchBrands, selectBrand } from '../lib/api'
import { filterOperatingBrandIds } from '../lib/brands'
import {
  readStoredScope,
  resolveInitialScope,
  scopeBrandIds,
  writeStoredScope,
  type BrandScope,
} from '../lib/brandScope'
import { prettyBrand, toneFor, TONE_CLS, type BrandTone } from '../lib/brandTone'
import { Tip } from './ui'

type BrandRow = { id: string; label: string; icon?: string; tone: BrandTone }

type BrandCtx = {
  brandId?: string
  brandLabel?: string
  brands: BrandRow[]
  busy: boolean
  setBrand: (id: string, label: string) => Promise<void>
}

const BrandContext = createContext<BrandCtx>({
  brands: [],
  busy: false,
  setBrand: async () => undefined,
})

type ScopeCtx = {
  scope: BrandScope
  brandIds: string[]
  isAll: boolean
  focusBrandId?: string
  setScopeAll: () => void
  setScopeBrand: (id: string, label: string) => Promise<void>
}

const BrandScopeContext = createContext<ScopeCtx>({
  scope: 'all',
  brandIds: [],
  isAll: true,
  setScopeAll: () => undefined,
  setScopeBrand: async () => undefined,
})

export function useBrand() {
  return useContext(BrandContext)
}

export function useBrandScope() {
  return useContext(BrandScopeContext)
}

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brandId, setId] = useState<string>()
  const [brandLabel, setLabel] = useState<string>()
  const [brands, setBrands] = useState<BrandRow[]>([])
  const [busy, setBusy] = useState(false)
  const [scope, setScope] = useState<BrandScope>('all')
  const scopeInitialized = useRef(false)

  useEffect(() => {
    fetchBrands()
      .then((payload) => {
        const rows = Object.entries(payload.brands || {})
          .map(([id, rec], index) => ({
            id,
            label: prettyBrand(id, rec),
            icon: rec.icon,
            tone: toneFor(id, prettyBrand(id, rec), index),
            order: typeof rec.order === 'number' ? rec.order : 99,
          }))
          .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
        setBrands(rows)
        const id = payload.active_brand_id || payload.default_brand_id || rows[0]?.id
        setId(id)
        setLabel(rows.find((row) => row.id === id)?.label || (id ? prettyBrand(id) : undefined))
        const orderedOperating = filterOperatingBrandIds(rows.map((r) => r.id))
        if (!scopeInitialized.current) {
          scopeInitialized.current = true
          const initial = resolveInitialScope(readStoredScope(), orderedOperating)
          setScope(initial)
        }
      })
      .catch(() => setBrands([]))
  }, [])

  async function setBrand(id: string, label: string) {
    if (id === brandId || busy) return
    setBusy(true)
    try {
      await selectBrand(id)
      setId(id)
      setLabel(label)
    } finally {
      setBusy(false)
    }
  }

  const operatingBrandIds = useMemo(() => filterOperatingBrandIds(brands.map((r) => r.id)), [brands])

  const brandIds = useMemo(() => scopeBrandIds(scope, operatingBrandIds), [scope, operatingBrandIds])

  function setScopeAll() {
    writeStoredScope('all')
    setScope('all')
  }

  async function setScopeBrand(id: string, label: string) {
    writeStoredScope(id)
    setScope(id)
    await setBrand(id, label)
  }

  return (
    <BrandContext.Provider value={{ brandId, brandLabel, brands, busy, setBrand }}>
      <BrandScopeContext.Provider
        value={{
          scope,
          brandIds,
          isAll: scope === 'all',
          focusBrandId: brandId,
          setScopeAll,
          setScopeBrand,
        }}
      >
        {children}
      </BrandScopeContext.Provider>
    </BrandContext.Provider>
  )
}

export function BrandSwitch({ variant = 'bar' }: { variant?: 'bar' | 'inline' }) {
  const { brandId, brandLabel, brands, busy } = useBrand()
  const { isAll, setScopeAll, setScopeBrand } = useBrandScope()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const label = isAll ? 'All brands' : brandLabel || 'Brand'

  useEffect(() => {
    function close(e: MouseEvent) {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  async function pick(id: string, nextLabel: string) {
    if (id === brandId && !isAll) {
      setOpen(false)
      return
    }
    await setScopeBrand(id, nextLabel)
    setOpen(false)
  }

  function pickAll() {
    setScopeAll()
    setOpen(false)
  }

  const bar = variant === 'bar'
  const current = isAll ? undefined : brands.find((row) => row.id === brandId)
  const currentTone = TONE_CLS[current?.tone || 'gold']
  const inlineTextTone = currentTone.bar.split(' ')[0]

  return (
    <span ref={box} className={`relative inline-flex ${bar ? 'shrink-0' : 'align-baseline'}`}>
      <Tip text="Switch the brand this desk is working on.">
        <button
          type="button"
          title="Switch the brand this desk is working on."
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className={
            bar
              ? `inline-flex items-center gap-2 rounded-full border bg-bg2 px-3 py-1.5 text-sm font-semibold ${
                  isAll ? 'text-tx2 border-bd hover:border-tx3' : currentTone.bar
                }`
              : `inline-flex cursor-pointer items-baseline gap-1.5 border-0 bg-transparent p-0 font-display text-[length:inherit] leading-[inherit] font-semibold ${
                  isAll ? 'text-tx2' : inlineTextTone
                } hover:opacity-90`
          }
        >
          {bar ? (
            isAll ? (
              <span aria-hidden className="flex h-2 w-2 shrink-0 gap-0.5">
                <span className="h-1 w-1 rounded-full bg-tx3" />
                <span className="h-1 w-1 rounded-full bg-tx3" />
                <span className="h-1 w-1 rounded-full bg-tx3" />
              </span>
            ) : (
              <span aria-hidden className={`h-2 w-2 rounded-full ${currentTone.swatch}`} />
            )
          ) : null}
          {label}
          <ChevronDown
            className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''} ${bar ? 'h-4 w-4' : 'h-[0.55em] w-[0.55em] min-h-[14px] min-w-[14px] opacity-85'}`}
            strokeWidth={2.5}
          />
        </button>
      </Tip>
      {open ? (
        <ul
          role="listbox"
          className="absolute top-full right-0 z-50 mt-2 min-w-[240px] rounded-2xl border border-white/15 bg-bg2 p-1.5 shadow-[0_18px_40px_rgba(0,0,0,.62)]"
        >
          <li>
            <button
              type="button"
              role="option"
              aria-selected={isAll}
              disabled={busy}
              title="Show every operating brand on this desk."
              onClick={pickAll}
              className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm ${
                isAll ? 'bg-[#1a1a1a] text-tx shadow-[inset_0_0_0_1.5px_rgba(255,255,255,.2)]' : 'text-tx hover:bg-white/8'
              }`}
            >
              <span aria-hidden className="flex h-2.5 w-2.5 shrink-0 items-center justify-center gap-px">
                <span className="h-1 w-1 rounded-full bg-tx3" />
                <span className="h-1 w-1 rounded-full bg-tx3" />
              </span>
              All brands
            </button>
          </li>
          {brands.map((brand) => {
            const tone = TONE_CLS[brand.tone]
            const on = !isAll && brand.id === brandId
            return (
              <li key={brand.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={on}
                  disabled={busy}
                  title={`Show the desk as ${brand.label}.`}
                  onClick={() => pick(brand.id, brand.label)}
                  className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm ${
                    on ? tone.on : 'text-tx hover:bg-white/8'
                  }`}
                >
                  <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${tone.swatch}`} />
                  {brand.label}
                </button>
              </li>
            )
          })}
          {brands.length === 0 ? (
            <li className="px-3 py-2 text-sm text-tx3">No other brands on this desk.</li>
          ) : null}
        </ul>
      ) : null}
    </span>
  )
}
