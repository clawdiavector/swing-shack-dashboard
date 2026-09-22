import { ChevronDown } from 'lucide-react'
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { fetchBrands, selectBrand, type BrandRecord } from '../lib/api'
import { Tip } from './ui'

function prettyBrand(id: string, rec?: BrandRecord) {
  return rec?.display_name || rec?.name || rec?.label || id.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

type BrandTone = 'gold' | 'green' | 'blue' | 'red'

const TONE_ORDER: BrandTone[] = ['gold', 'green', 'blue', 'red']

const TONE_CLS: Record<
  BrandTone,
  { on: string; bar: string; swatch: string }
> = {
  gold: {
    on: 'bg-[#2a2210] text-yel shadow-[inset_0_0_0_1.5px_rgba(251,191,36,.85)]',
    bar: 'text-yel border-yel/50 hover:border-yel',
    swatch: 'bg-yel',
  },
  green: {
    on: 'bg-[#0f2a22] text-ac shadow-[inset_0_0_0_1.5px_rgba(52,211,153,.85)]',
    bar: 'text-ac border-ac/50 hover:border-ac',
    swatch: 'bg-ac',
  },
  blue: {
    on: 'bg-[#132033] text-blu shadow-[inset_0_0_0_1.5px_rgba(96,165,250,.85)]',
    bar: 'text-blu border-blu/50 hover:border-blu',
    swatch: 'bg-blu',
  },
  red: {
    on: 'bg-[#2a1518] text-red shadow-[inset_0_0_0_1.5px_rgba(248,113,113,.85)]',
    bar: 'text-red border-red/50 hover:border-red',
    swatch: 'bg-red',
  },
}

function toneFor(id: string, label: string, index: number): BrandTone {
  const key = `${id} ${label}`.toLowerCase()
  if (key.includes('swing')) return 'gold'
  if (key.includes('stick')) return 'green'
  if (key.includes('bag')) return 'blue'
  return TONE_ORDER[index % TONE_ORDER.length]
}

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

export function useBrand() {
  return useContext(BrandContext)
}

export function BrandProvider({ children }: { children: ReactNode }) {
  const [brandId, setId] = useState<string>()
  const [brandLabel, setLabel] = useState<string>()
  const [brands, setBrands] = useState<BrandRow[]>([])
  const [busy, setBusy] = useState(false)

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

  return (
    <BrandContext.Provider value={{ brandId, brandLabel, brands, busy, setBrand }}>
      {children}
    </BrandContext.Provider>
  )
}

export function BrandSwitch({ variant = 'bar' }: { variant?: 'bar' | 'inline' }) {
  const { brandId, brandLabel, brands, busy, setBrand } = useBrand()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const label = brandLabel || 'Brand'

  useEffect(() => {
    function close(e: MouseEvent) {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  async function pick(id: string, nextLabel: string) {
    if (id === brandId) {
      setOpen(false)
      return
    }
    await setBrand(id, nextLabel)
    setOpen(false)
  }

  const bar = variant === 'bar'
  const current = brands.find((row) => row.id === brandId)
  const currentTone = TONE_CLS[current?.tone || 'gold']

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
              ? `inline-flex items-center gap-2 rounded-full border bg-bg2 px-3 py-1.5 text-sm font-semibold ${currentTone.bar}`
              : `inline-flex cursor-pointer items-baseline gap-1.5 border-0 bg-transparent p-0 font-[inherit] text-[length:inherit] leading-[inherit] ${currentTone.bar.split(' ')[0]}`
          }
        >
          <span aria-hidden className={`h-2 w-2 rounded-full ${currentTone.swatch}`} />
          {label}
          <ChevronDown
            className={`${bar ? 'h-4 w-4' : 'h-7 w-7 self-center'} shrink-0 ${open ? 'rotate-180' : ''}`}
            strokeWidth={2.5}
          />
        </button>
      </Tip>
      {open ? (
        <ul
          role="listbox"
          className="absolute top-full right-0 z-50 mt-2 min-w-[240px] rounded-2xl border border-white/15 bg-bg2 p-1.5 shadow-[0_18px_40px_rgba(0,0,0,.62)]"
        >
          {brands.map((brand) => {
            const tone = TONE_CLS[brand.tone]
            const on = brand.id === brandId
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
