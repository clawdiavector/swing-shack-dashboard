import type { BrandSocialLink } from '../lib/api'

export type DailyBrandSocialsRow = {
  brandId: string
  brandLabel: string
  socials: BrandSocialLink[]
}

type DailyBrandSocialsProps = {
  rows: DailyBrandSocialsRow[]
}

export function DailyBrandSocials({ rows }: DailyBrandSocialsProps) {
  const visible = rows.filter((row) => row.socials.length > 0)
  if (!visible.length) return null

  return (
    <section
      className="space-y-3 rounded-2xl border border-bd bg-surface/40 px-4 py-3"
      aria-label="Brand social profiles"
      data-testid="daily-socials"
    >
      <p className="text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase">Socials</p>
      <ul className="space-y-3">
        {visible.map((row) => (
          <li key={row.brandId} className="space-y-2">
            {visible.length > 1 ? (
              <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">{row.brandLabel}</p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {row.socials.map((link) => (
                <a
                  key={`${row.brandId}-${link.platform}-${link.url}`}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-display inline-flex items-center rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-sm font-semibold text-tx2 hover:border-ac/50 hover:text-tx"
                >
                  {link.label}
                </a>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
