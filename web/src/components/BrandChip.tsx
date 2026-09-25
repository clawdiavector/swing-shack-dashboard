import { useBrand } from './BrandSwitch'
import { prettyBrand, toneFor, TONE_CLS } from '../lib/brandTone'

export function BrandChip({ brandId, show = true }: { brandId?: string; show?: boolean }) {
  if (!show || !brandId) return null
  const { brands } = useBrand()
  const row = brands.find((b) => b.id === brandId)
  const label = row?.label || prettyBrand(brandId)
  const tone = row?.tone ?? toneFor(brandId, label, 0)
  const cls = TONE_CLS[tone]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2 py-0.5 text-xs font-semibold ${cls.on}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${cls.swatch}`} />
      {label}
    </span>
  )
}
