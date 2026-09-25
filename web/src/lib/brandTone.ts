import type { BrandRecord } from './api'

export type BrandTone = 'gold' | 'green' | 'blue' | 'red'

export const TONE_ORDER: BrandTone[] = ['gold', 'green', 'blue', 'red']

export const TONE_CLS: Record<
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

export function prettyBrand(id: string, rec?: BrandRecord) {
  return rec?.display_name || rec?.name || rec?.label || id.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function toneFor(id: string, label: string, index: number): BrandTone {
  const key = `${id} ${label}`.toLowerCase()
  if (key.includes('swing')) return 'gold'
  if (key.includes('stick')) return 'green'
  if (key.includes('bag')) return 'blue'
  return TONE_ORDER[index % TONE_ORDER.length]
}
