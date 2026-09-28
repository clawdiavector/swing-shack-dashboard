import type { InboxItem } from './api'
import type { TemplateMeta } from '../components/TemplateReferenceTag'
import type { PostingWeekPost } from './postingWeek'

function pickTemplateFields(source: TemplateMeta | null | undefined): TemplateMeta | null {
  if (!source?.template_id && !source?.template_label) return null
  return {
    template_id: source.template_id,
    template_name: source.template_name,
    template_label: source.template_label,
    template_reference_urls: source.template_reference_urls,
  }
}

export function templateMetaFromPost(post: PostingWeekPost): TemplateMeta | null {
  return pickTemplateFields(post)
}

export function templateMetaFromInbox(item: InboxItem): TemplateMeta | null {
  const meta = item.meta as TemplateMeta | undefined
  const fromMeta = pickTemplateFields(meta)
  if (fromMeta) return fromMeta
  const arch = item.meta?.archetype
  const archId = typeof arch === 'object' && arch && 'id' in arch ? String(arch.id || '') : ''
  if (!archId) return null
  return { template_id: archId, template_label: archId.replace(/^stick-|^ss-/, '').replace(/-/g, ' ') }
}
