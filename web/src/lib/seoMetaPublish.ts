// Shape of GET /api/seo/meta-publish (campaign-os/_lib/seo_meta_publish.py).

export type PublishMode = 'off' | 'dry-run' | 'on'

export interface MetaChange {
  id: string
  page: string
  // Absent on changes written before the buttons existed: those were search descriptions.
  field?: 'meta_description' | 'title'
  // 'button' when a person clicked Fix or Improve; absent for the automatic check.
  source?: 'button'
  link: string | null
  before: string
  after: string
  at: string
  status: 'dry_run' | 'applied' | 'failed' | 'undone'
  verified?: boolean
  error?: string
  undone_at?: string
}

export function modeNote(mode: PublishMode): string {
  switch (mode) {
    case 'on':
      return 'Automatic publishing is on. Search descriptions that are missing get filled in, and every change can be undone.'
    case 'dry-run':
      return 'Practice mode. The changes below are what would be written. Nothing on the website has been changed.'
    default:
      return 'Automatic publishing is switched off. Nothing is changed on the website.'
  }
}

export function statusLabel(c: MetaChange): string {
  switch (c.status) {
    case 'applied':
      return c.verified === false ? 'Changed (not confirmed)' : 'Changed'
    case 'dry_run':
      return 'Would change'
    case 'undone':
      return 'Undone'
    default:
      return 'Did not work'
  }
}

export const canUndo = (c: MetaChange): boolean => c.status === 'applied'
