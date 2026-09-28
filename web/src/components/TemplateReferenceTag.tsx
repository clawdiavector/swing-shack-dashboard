import { X } from 'lucide-react'
import { useEffect, useState, type MouseEvent } from 'react'
import { createPortal } from 'react-dom'
import { resolveAssetUrl } from '../lib/api'
import { Badge } from './ui'

export type TemplateMeta = {
  template_id?: string
  template_name?: string
  template_label?: string
  template_reference_urls?: string[]
}

export function templateMetaFromRecord(
  row: TemplateMeta | null | undefined,
): TemplateMeta | null {
  if (!row?.template_id && !row?.template_label) return null
  return row
}

function TemplateReferenceModal({
  open,
  onClose,
  meta,
  label,
  urls,
}: {
  open: boolean
  onClose: () => void
  meta: TemplateMeta | null
  label: string
  urls: string[]
}) {
  const [refIndex, setRefIndex] = useState(0)

  useEffect(() => {
    if (!open) return
    setRefIndex(0)
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || typeof document === 'undefined') return null

  const refUrl = urls[refIndex] || urls[0]

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Template reference — ${label}`}
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-bd bg-bg p-4 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold uppercase tracking-wide text-tx3">Template reference</p>
            <h3 className="font-display text-lg font-semibold leading-snug text-tx">
              {meta?.template_name || label}
            </h3>
            {meta?.template_id ? (
              <p className="mt-1 font-mono text-xs text-tx3">{meta.template_id}</p>
            ) : null}
          </div>
          <button
            type="button"
            aria-label="Close"
            className="rounded-full border border-bd p-1.5 hover:border-ac"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {refUrl ? (
          <>
            {urls.length > 1 ? (
              <div className="mb-2 flex items-center justify-between text-xs text-tx3">
                <span>
                  Reference {refIndex + 1} of {urls.length}
                </span>
                <span className="flex gap-1">
                  <button
                    type="button"
                    className="rounded border border-bd px-2 py-0.5 disabled:opacity-40"
                    disabled={refIndex <= 0}
                    onClick={() => setRefIndex((i) => Math.max(0, i - 1))}
                  >
                    Prev
                  </button>
                  <button
                    type="button"
                    className="rounded border border-bd px-2 py-0.5 disabled:opacity-40"
                    disabled={refIndex >= urls.length - 1}
                    onClick={() => setRefIndex((i) => Math.min(urls.length - 1, i + 1))}
                  >
                    Next
                  </button>
                </span>
              </div>
            ) : null}
            <img
              src={refUrl}
              alt={`Reference for ${label}`}
              className="mx-auto max-h-[min(75vh,32rem)] w-full object-contain"
            />
          </>
        ) : (
          <p className="rounded-xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
            No reference images indexed for this template yet.
          </p>
        )}
      </div>
    </div>,
    document.body,
  )
}

export function TemplateReferenceTag({
  meta,
  onClickCapture,
  /** Queue cards: tag only — open piece and use compare toggle there. */
  preview = 'modal',
}: {
  meta: TemplateMeta | null
  onClickCapture?: (event: MouseEvent) => void
  preview?: 'modal' | 'label-only'
}) {
  const [open, setOpen] = useState(false)
  const label = meta?.template_label || meta?.template_id
  const urls = (meta?.template_reference_urls || [])
    .map((u) => resolveAssetUrl(u))
    .filter(Boolean)

  if (!label) return null

  if (preview === 'label-only') {
    return (
      <span title={meta?.template_name || label}>
        <Badge tone="blue">
          <span className="truncate">Tpl · {label}</span>
        </Badge>
      </span>
    )
  }

  return (
    <>
      <button
        type="button"
        title={meta?.template_name || 'View template reference art'}
        onClick={(event) => {
          onClickCapture?.(event)
          event.preventDefault()
          event.stopPropagation()
          setOpen(true)
        }}
        className="inline-flex max-w-full"
      >
        <Badge tone="blue">
          <span className="truncate">Tpl · {label}</span>
        </Badge>
      </button>
      <TemplateReferenceModal
        open={open}
        onClose={() => setOpen(false)}
        meta={meta}
        label={label}
        urls={urls}
      />
    </>
  )
}
