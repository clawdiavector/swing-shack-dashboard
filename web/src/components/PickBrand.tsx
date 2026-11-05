import { filterOperatingBrandIds } from '../lib/brands'
import { useBrand, useBrandScope } from './BrandSwitch'

type Pickable = { id: string; label: string }

/** The operating brands from the brand list, in its order. */
export function pickableBrands<T extends Pickable>(rows: T[]): T[] {
  const keep = new Set(filterOperatingBrandIds(rows.map((r) => r.id)))
  return rows.filter((r) => keep.has(r.id))
}

export function PickBrandButtons({
  message,
  brands,
  onPick,
}: {
  message: string
  brands: Pickable[]
  onPick: (id: string, label: string) => void
}) {
  return (
    <div className="glass rounded-2xl border border-white/10 p-6">
      <p className="text-sm text-tx2">{message}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {brands.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => onPick(b.id, b.label)}
            className="rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac hover:text-ac"
          >
            {b.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Shown on a per-brand page while "All brands" is picked: one tap picks the brand here. */
export function PickBrand({ message }: { message: string }) {
  const { brands } = useBrand()
  const { setScopeBrand } = useBrandScope()
  return (
    <PickBrandButtons
      message={message}
      brands={pickableBrands(brands)}
      onPick={(id, label) => void setScopeBrand(id, label)}
    />
  )
}
