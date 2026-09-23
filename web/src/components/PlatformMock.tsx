import { useState } from 'react'
import type { PlatformTab } from '../lib/platformMock'

export function PlatformMock({
  platform,
  imageUrl,
  caption,
  brandId,
}: {
  platform: PlatformTab
  imageUrl: string
  caption: string
  brandId?: string
}) {
  const [imgBroken, setImgBroken] = useState(false)
  const handle = brandId ? `@${brandId.replace(/-/g, '')}` : '@brand'
  const showImage = Boolean(imageUrl) && !imgBroken

  return (
    <div className="glass rounded-2xl border border-white/10 p-4">
      {platform === 'instagram' ? (
        <div className="mb-3 flex items-center gap-2 text-sm">
          <div className="h-8 w-8 rounded-full bg-bg3" />
          <span className="font-semibold text-tx">{handle}</span>
        </div>
      ) : null}
      {platform === 'facebook' ? (
        <div className="mb-3 flex items-center gap-2 text-sm">
          <div className="h-9 w-9 rounded-full bg-bg3" />
          <div>
            <p className="font-semibold text-tx">{brandId || 'Brand page'}</p>
            <p className="text-xs text-tx3">Just now · 🌐</p>
          </div>
        </div>
      ) : null}
      {platform === 'gbp' ? (
        <div className="mb-3 text-sm">
          <p className="font-semibold text-tx">{brandId || 'Business'}</p>
          <p className="text-xs text-tx3">Google Business Profile · Update</p>
        </div>
      ) : null}

      {showImage ? (
        <img
          src={imageUrl}
          alt=""
          onError={() => setImgBroken(true)}
          className="mb-3 w-full rounded-xl border border-bd object-cover"
        />
      ) : (
        <div className="mb-3 rounded-xl border border-dashed border-bd px-4 py-8 text-center text-sm text-tx3">
          No image on this queue row.
        </div>
      )}

      <p className="whitespace-pre-wrap text-sm text-tx2">{caption || '—'}</p>

      {platform === 'instagram' ? (
        <p className="mt-3 text-xs text-tx3">♡ 💬 ↗ · Instagram mock — not live</p>
      ) : null}
      {platform === 'facebook' ? (
        <p className="mt-3 text-xs text-tx3">👍 Comment Share · Facebook mock — not live</p>
      ) : null}
      {platform === 'gbp' ? (
        <p className="mt-3 text-xs text-tx3">Call · Directions · Website · GBP mock — not live</p>
      ) : null}
    </div>
  )
}
