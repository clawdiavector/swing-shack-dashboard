/** Helpers for the post studio page (slug + default go-live date). */

export function slugFromCaption(caption: string, fallback = 'post'): string {
  const words = caption
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 6)
  const base = words.join('-').replace(/-+/g, '-').slice(0, 48)
  const slug = (base || fallback).replace(/^-+|-+$/g, '')
  if (slug.length >= 2) return slug
  return `${fallback}-${Date.now().toString(36).slice(-4)}`
}

/** Johannesburg calendar date, default two days ahead (matches lodge validation). */
export function defaultGoLiveDate(offsetDays = 2): string {
  const now = new Date()
  const jhb = new Date(now.toLocaleString('en-US', { timeZone: 'Africa/Johannesburg' }))
  jhb.setDate(jhb.getDate() + offsetDays)
  const y = jhb.getFullYear()
  const m = String(jhb.getMonth() + 1).padStart(2, '0')
  const d = String(jhb.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function brandPhotoPath(brandId: string, filename: string): string {
  const fn = filename.split('/').pop() || filename
  return `data/brand-directory/${brandId}/images/${fn}`
}
