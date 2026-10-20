// Shape of GET /api/seo/fix-queue (campaign-os/_lib/seo_fix_queue.py).

export interface SeoFix {
  id: string
  source: 'seo' | 'geo'
  type: string
  page: string | null
  severity: 'high' | 'medium' | 'low' | null
  message: string | null
  fix: string | null
  publish_policy: 'auto_with_undo' | 'asks_first'
  status: 'draft' | 'dismissed' | 'done' | 'resolved'
  first_seen: string
}

export interface SeoFixQueue {
  brand: string
  updated: string
  counts: { open: number; auto_eligible: number; asks_first: number }
  items: SeoFix[]
}

const SEVERITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

function bySeverityThenPage(a: SeoFix, b: SeoFix): number {
  const s = (SEVERITY_RANK[a.severity ?? ''] ?? 3) - (SEVERITY_RANK[b.severity ?? ''] ?? 3)
  if (s !== 0) return s
  return (a.page ?? '').localeCompare(b.page ?? '') || a.type.localeCompare(b.type)
}

// Open fixes only (status draft), split by what may happen to them, worst first.
export function groupFixes(queue: SeoFixQueue | null): { auto: SeoFix[]; ask: SeoFix[] } {
  const open = (queue?.items ?? []).filter((i) => i.status === 'draft')
  return {
    auto: open.filter((i) => i.publish_policy === 'auto_with_undo').sort(bySeverityThenPage),
    ask: open.filter((i) => i.publish_policy !== 'auto_with_undo').sort(bySeverityThenPage),
  }
}

// The audit's own sentence is long and technical; a short plain label per type.
const LABELS: Record<string, string> = {
  missing_title: 'No page title',
  title_too_short: 'Title too short',
  title_too_long: 'Title too long',
  missing_meta_description: 'No search description',
  meta_description_short: 'Search description too short',
  missing_h1: 'No main heading',
  multiple_h1: 'More than one main heading',
  images_missing_alt: 'Images without descriptions',
  missing_faq: 'No questions-and-answers section',
  no_qa_blocks: 'No questions-and-answers section',
  missing_local_signals: 'Location not mentioned',
  weak_internal_linking: 'Few links to other pages',
  unclear_entity: 'Unclear who provides the service',
  unclear_offering: 'Unclear what the service is',
  missing_location: 'Location missing',
  missing_price: 'Price missing',
  missing_duration: 'Session length missing',
  missing_cta: 'No clear booking button',
  no_structured_data: 'No structured data for search engines',
  thin_content: 'Very little text on the page',
}

export function fixLabel(type: string): string {
  return LABELS[type] ?? type.replace(/_/g, ' ')
}
