// Shapes and wording for the Fix / Improve buttons
// (POST /api/seo/fix/draft and /api/seo/fix/apply, campaign-os/_lib/seo_fixer.py).

import type { MetaChange, PublishMode } from './seoMetaPublish'

export interface FixDraft {
  ok: boolean
  error?: string
  mode?: PublishMode
  item_id?: string
  page?: string
  field?: 'meta_description' | 'title'
  field_label?: string
  button?: 'Fix' | 'Improve'
  // false: WordPress will not save this field on this kind of page (Yoast hides it from pages).
  // null or missing: unknown, so Apply is offered and the read-back decides.
  writable?: boolean | null
  unwritable_reason?: string | null
  current?: string
  proposal?: string | null
  min?: number
  max?: number
  notes?: string[]
}

export interface ApplyResult {
  ok: boolean
  error?: string
  needs_confirm?: boolean
  warnings?: string[]
  mode?: PublishMode
  entry?: MetaChange
}

const FIELD_LABELS: Record<string, string> = {
  meta_description: 'Search description',
  title: 'Page title',
}

// Entries written before the buttons existed have no field: they were descriptions.
export const fieldLabel = (field?: string): string => FIELD_LABELS[field ?? 'meta_description'] ?? 'Search result text'

export type LengthState = 'short' | 'long' | 'ok'

export function lengthState(text: string, min: number, max: number): { count: number; state: LengthState; hint: string } {
  const count = text.trim().replace(/\s+/g, ' ').length
  if (count < min) return { count, state: 'short', hint: `${count} characters. Needs at least ${min}.` }
  if (count > max) return { count, state: 'long', hint: `${count} characters. Needs at most ${max}, or Google cuts it off.` }
  return { count, state: 'ok', hint: `${count} characters. Good length (${min} to ${max}).` }
}

// What the person is told after clicking Apply, by what actually happened.
export function resultNote(r: ApplyResult): { ok: boolean; text: string } {
  if (!r.ok) return { ok: false, text: r.error || 'Could not apply that.' }
  const status = r.entry?.status
  if (status === 'dry_run') {
    return { ok: true, text: 'Practice mode: recorded as "would change". Nothing on the website was changed.' }
  }
  if (status === 'applied' && r.entry?.verified === false) {
    return { ok: true, text: 'Sent to the website, but it could not be confirmed. Check the page.' }
  }
  return { ok: true, text: 'Changed on the website and confirmed. Undo is under Changes made.' }
}

// True when the page must offer the text to copy instead of an Apply button.
export const cannotSave = (d: Pick<FixDraft, 'writable'>): boolean => d.writable === false

// Only a change that really reached the website closes the item on the page.
export const closesItem = (r: ApplyResult): boolean => r.ok && r.entry?.status === 'applied'
