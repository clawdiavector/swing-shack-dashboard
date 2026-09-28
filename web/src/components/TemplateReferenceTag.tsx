import { X } from 'lucide-react'
import { useEffect, useState, type MouseEvent } from 'react'
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

export function TemplateReferenceTag({
  meta,
  onClickCapture,
}: {
  meta: TemplateMeta | null
  /** Stop navigation when the tag sits inside a link card. */
  onClickCapture?: (event: MouseEvent) => void
}) {
  const [open, setOpen] = useState(false)
  const label = meta?.template_label || meta?.template_id
  const urls = (meta?.template_reference_urls || [])
    .map((u) => resolveAssetUrl(u))
    .filter(Boolean)

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!label) return null

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

      {open ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={`Template reference — ${label}`}
          onClick={(event) => {
            event.stopPropagation()
            setOpen(false)
          }}
        >
          <div
            className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-bd bg-bg p-4 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[12px] font-semibold uppercase tracking-wide text-tx3">Template</p>
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
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {urls.length ? (
              <ul className="grid gap-3 sm:grid-cols-2">
                {urls.map((url) => (
                  <li key={url} className="overflow-hidden rounded-xl border border-bd bg-bg2/30">
                    <img
                      src={url}
                      alt={`Reference for ${label}`}
                      className="max-h-[min(70vh,28rem)] w-full object-contain"
                    />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                No reference images indexed for this template yet.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </>
  )
}
