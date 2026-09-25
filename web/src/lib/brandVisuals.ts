import {
  deleteBrandReference,
  postBrandReference,
  type BrandVisualDriveItem,
  type BrandVisualSocialItem,
} from './api'

export const SOCIAL_PLATFORMS = ['instagram', 'facebook'] as const
export type SocialPlatform = (typeof SOCIAL_PLATFORMS)[number]

export const DRIVE_GROUP_ORDER = ['Services', 'Products', 'Other'] as const
export type DriveGroupLabel = (typeof DRIVE_GROUP_ORDER)[number]

export function socialPlatformsFromChannels(channels: string[] | undefined): SocialPlatform[] {
  const set = new Set((channels || []).map((c) => c.toLowerCase()))
  return SOCIAL_PLATFORMS.filter((p) => set.has(p))
}

export function platformTabLabel(platform: SocialPlatform): string {
  const name = platform.charAt(0).toUpperCase() + platform.slice(1)
  return `On ${name}`
}

export function driveGroupLabel(folder: string): DriveGroupLabel {
  const f = folder.trim().toLowerCase()
  if (f === 'services' || f.startsWith('service')) return 'Services'
  if (f === 'products' || f === 'product') return 'Products'
  return 'Other'
}

export function groupDriveAssets(items: BrandVisualDriveItem[]): Record<DriveGroupLabel, BrandVisualDriveItem[]> {
  const out: Record<DriveGroupLabel, BrandVisualDriveItem[]> = {
    Services: [],
    Products: [],
    Other: [],
  }
  for (const item of items) {
    out[driveGroupLabel(item.folder || 'other')].push(item)
  }
  return out
}

export function socialEngagement(metrics?: Record<string, unknown>): string {
  if (!metrics) return ''
  const likes = metrics.likes ?? metrics.like_count ?? metrics.reactions
  const comments = metrics.comments ?? metrics.comment_count
  const parts: string[] = []
  if (likes != null && likes !== '') parts.push(`${likes} likes`)
  if (comments != null && comments !== '') parts.push(`${comments} comments`)
  return parts.join(' · ')
}

export function shortCaption(text: string | undefined, max = 80): string {
  const t = (text || '').trim()
  if (t.length <= max) return t
  return `${t.slice(0, max - 1)}…`
}

export function patchSocialReference(
  items: BrandVisualSocialItem[],
  id: string,
  isReference: boolean,
): BrandVisualSocialItem[] {
  return items.map((row) => (row.id === id ? { ...row, is_reference: isReference } : row))
}

export function patchDriveReference(
  items: BrandVisualDriveItem[],
  id: string,
  isReference: boolean,
): BrandVisualDriveItem[] {
  return items.map((row) => (row.id === id ? { ...row, is_reference: isReference } : row))
}

export async function toggleBrandReference(
  brandId: string,
  assetId: string,
  currentlyReference: boolean,
  source: 'social' | 'drive',
  platform?: string,
): Promise<void> {
  if (currentlyReference) {
    await deleteBrandReference(brandId, assetId)
    return
  }
  await postBrandReference(brandId, {
    source,
    id: assetId,
    platform: source === 'social' ? platform : undefined,
  })
}
