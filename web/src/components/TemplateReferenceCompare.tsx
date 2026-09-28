import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'
import { resolveAssetUrl } from '../lib/api'
import type { TemplateMeta } from './TemplateReferenceTag'

export function TemplateReferenceCompare({
  draftUrl,
  draftAlt,
  templateMeta,
  draftBroken,
  onDraftBroken,
  maxHeightClass = 'max-h-[min(50vh,22rem)]',
}: {
  draftUrl: string | null
  draftAlt: string
  templateMeta: TemplateMeta | null
  draftBroken?: boolean
  onDraftBroken?: () => void
  maxHeightClass?: string
}) {
  const refUrls = useMemo(
    () => (templateMeta?.template_reference_urls || []).map((u) => resolveAssetUrl(u)).filter(Boolean),
    [templateMeta],
  )
  const [compare, setCompare] = useState(false)
  const [refIndex, setRefIndex] = useState(0)
  const hasRefs = refUrls.length > 0
  const refUrl = refUrls[refIndex] || ''

  const imgClass = `mx-auto w-full rounded-2xl border border-bd object-contain ${maxHeightClass}`

  return (
    <div className="space-y-2">
      {hasRefs ? (
        <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-tx2">
          <input
            type="checkbox"
            checked={compare}
            onChange={(e) => setCompare(e.target.checked)}
            className="h-4 w-4 rounded border-bd accent-[var(--ac)]"
            data-testid="template-compare-toggle"
          />
          Compare to template reference
        </label>
      ) : null}

      {compare && hasRefs ? (
        <div className="grid gap-3 md:grid-cols-2 md:items-start">
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-tx3">Draft post</p>
            {draftUrl && !draftBroken ? (
              <a href={draftUrl} target="_blank" rel="noreferrer" className="block">
                <img src={draftUrl} alt={draftAlt} className={imgClass} onError={onDraftBroken} />
              </a>
            ) : (
              <p className="rounded-2xl border border-dashed border-bd px-3 py-8 text-center text-sm text-tx3">
                No draft image
              </p>
            )}
          </div>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-tx3">
                Template reference
                {refUrls.length > 1 ? ` (${refIndex + 1}/${refUrls.length})` : ''}
              </p>
              {refUrls.length > 1 ? (
                <div className="flex gap-1">
                  <button
                    type="button"
                    aria-label="Previous reference"
                    disabled={refIndex <= 0}
                    className="rounded-full border border-bd p-1 disabled:opacity-40"
                    onClick={() => setRefIndex((i) => Math.max(0, i - 1))}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    aria-label="Next reference"
                    disabled={refIndex >= refUrls.length - 1}
                    className="rounded-full border border-bd p-1 disabled:opacity-40"
                    onClick={() => setRefIndex((i) => Math.min(refUrls.length - 1, i + 1))}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              ) : null}
            </div>
            {refUrl ? (
              <a href={refUrl} target="_blank" rel="noreferrer" className="block">
                <img
                  src={refUrl}
                  alt={`Template reference ${templateMeta?.template_label || ''}`}
                  className={imgClass}
                />
              </a>
            ) : null}
            {templateMeta?.template_name ? (
              <p className="text-xs text-tx3">{templateMeta.template_name}</p>
            ) : null}
          </div>
        </div>
      ) : draftUrl && !draftBroken ? (
        <a href={draftUrl} target="_blank" rel="noreferrer" className="block">
          <img src={draftUrl} alt={draftAlt} className={imgClass} onError={onDraftBroken} />
        </a>
      ) : null}
    </div>
  )
}
