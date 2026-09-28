import { ChevronDown, ChevronUp, Layers, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useBrand } from '../../components/BrandSwitch'
import { PageIntro } from '../../components/chrome'
import { Badge, QueueItemThumb } from '../../components/ui'
import {
  fetchTemplateGallery,
  resolveAssetUrl,
  type TemplateGalleryTemplate,
} from '../../lib/api'

function BulletList({ items, empty }: { items?: string[]; empty: string }) {
  if (!items?.length) {
    return <p className="text-sm text-tx3">{empty}</p>
  }
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-tx2">
      {items.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  )
}

function PaletteSwatches({
  rows,
}: {
  rows?: { role: string; name: string; hex: string }[]
}) {
  if (!rows?.length) return null
  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {rows.map((row) => (
        <li
          key={row.role}
          className="flex items-center gap-2 rounded-lg border border-white/10 bg-bg2/60 px-2 py-1 text-xs"
        >
          <span
            className="h-4 w-4 rounded border border-white/20"
            style={{ backgroundColor: row.hex }}
            aria-hidden
          />
          <span className="text-tx2">{row.name}</span>
          <span className="font-mono text-tx3">{row.hex}</span>
        </li>
      ))}
    </ul>
  )
}

function CoverageStatusBadge({ status }: { status?: TemplateGalleryTemplate['status'] }) {
  if (!status) return null
  const tone =
    status === 'ready' ? 'green' : status === 'partial' ? 'gold' : ('mute' as const)
  const label = status === 'ready' ? 'Ready' : status === 'partial' ? 'Partial' : 'Missing'
  return <Badge tone={tone}>{label}</Badge>
}

function CoverageSummaryBar({
  ready,
  partial,
  missing,
}: {
  ready: number
  partial: number
  missing: number
}) {
  return (
    <div className="glass flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 px-5 py-3 text-sm">
      <span className="font-semibold text-tx">Coverage</span>
      <span className="text-tx2">
        <span className="font-semibold text-green">{ready}</span> ready
        <span className="mx-2 text-tx3">·</span>
        <span className="font-semibold text-yel">{partial}</span> partial
        <span className="mx-2 text-tx3">·</span>
        <span className="font-semibold text-tx3">{missing}</span> missing
      </span>
    </div>
  )
}

function TemplateCard({
  template,
  onSelect,
}: {
  template: TemplateGalleryTemplate
  onSelect: (t: TemplateGalleryTemplate) => void
}) {
  const thumb = resolveAssetUrl(template.preview_urls?.[0])
  return (
    <button
      type="button"
      onClick={() => onSelect(template)}
      className="glass flex flex-col overflow-hidden rounded-2xl border border-white/10 text-left transition hover:border-ac/40"
    >
      <div className="relative aspect-[4/5] w-full bg-bg2">
        {thumb ? (
          <QueueItemThumb
            src={thumb}
            alt={template.label}
            className="h-full w-full rounded-none border-0 object-cover"
          />
        ) : (
          <div className="grid h-full place-items-center text-xs text-tx3">No preview</div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-tx">{template.label}</p>
          <CoverageStatusBadge status={template.status} />
        </div>
        <div className="flex flex-wrap gap-1">
          {template.canvas ? <Badge tone="mute">{template.canvas}</Badge> : null}
          <Badge tone={template.needs_photo ? 'gold' : 'green'}>
            {template.needs_photo ? 'Photo' : 'Compose only'}
          </Badge>
        </div>
      </div>
    </button>
  )
}

function DetailDrawer({
  template,
  onClose,
}: {
  template: TemplateGalleryTemplate
  onClose: () => void
}) {
  const previews = useMemo(
    () => (template.preview_urls || []).map((u) => resolveAssetUrl(u)).filter(Boolean),
    [template.preview_urls],
  )
  const [slide, setSlide] = useState(0)
  const active = previews[slide] || ''

  useEffect(() => {
    setSlide(0)
  }, [template.template_id])

  const bodyText = template.description || template.notes || ''

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal
      aria-label={template.label}
    >
      <div className="glass max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/15 p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-xl font-semibold">{template.label}</h2>
              <CoverageStatusBadge status={template.status} />
            </div>
            <p className="mt-1 text-sm text-tx3">{template.name || template.archetype_id}</p>
            {template.archetype_id ? (
              <p className="mt-1 font-mono text-xs text-tx3">{template.archetype_id}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 hover:bg-white/10"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {active ? (
          <div className="mb-4 overflow-hidden rounded-xl border border-white/10">
            <QueueItemThumb
              src={active}
              alt={template.label}
              className="max-h-80 w-full object-contain bg-bg2"
            />
            {previews.length > 1 ? (
              <div className="flex gap-2 overflow-x-auto border-t border-white/10 p-2">
                {previews.map((url, i) => (
                  <button
                    key={url}
                    type="button"
                    onClick={() => setSlide(i)}
                    className={`shrink-0 overflow-hidden rounded-lg border-2 ${
                      i === slide ? 'border-ac' : 'border-transparent'
                    }`}
                  >
                    <img src={url} alt="" className="h-14 w-14 object-cover" />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {bodyText ? <p className="mb-4 text-sm text-tx2">{bodyText}</p> : null}

        {template.content_bank_hint ? (
          <div className="mb-4 rounded-xl border border-white/10 bg-bg2/50 px-3 py-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-tx3">
              Content bank
            </h3>
            <p className="mt-1 text-sm text-tx2">{template.content_bank_hint}</p>
          </div>
        ) : null}

        {template.sections?.length ? (
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-tx">Zones</h3>
            <ul className="mt-2 flex flex-wrap gap-1">
              {template.sections.map((z) => (
                <li key={z}>
                  <Badge tone="mute">{z}</Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {template.post_type_hints?.length ? (
          <p className="mb-4 text-xs text-tx3">
            Post types: {template.post_type_hints.join(', ')}
          </p>
        ) : null}

        {template.template_md_excerpt ? (
          <div className="mb-2">
            <h3 className="text-sm font-semibold text-tx">template.md</h3>
            <pre className="mt-2 max-h-48 overflow-auto rounded-xl border border-white/10 bg-bg2/80 p-3 text-xs whitespace-pre-wrap text-tx2">
              {template.template_md_excerpt}
            </pre>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function RoadmapTable({
  rows,
  onSelect,
}: {
  rows: TemplateGalleryTemplate[]
  onSelect: (t: TemplateGalleryTemplate) => void
}) {
  if (!rows.length) {
    return <p className="text-sm text-tx3">No roadmap rows for this brand.</p>
  }
  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <thead className="border-b border-white/10 bg-bg2/60 text-xs uppercase text-tx3">
          <tr>
            <th className="px-4 py-3 font-semibold">Family</th>
            <th className="px-4 py-3 font-semibold">Archetype</th>
            <th className="px-4 py-3 font-semibold">Section</th>
            <th className="px-4 py-3 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.archetype_id || row.template_id} className="border-b border-white/5">
              <td className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => onSelect(row)}
                  className="font-medium text-ac hover:underline text-left"
                >
                  {row.label}
                  {row.wave === 2 ? (
                    <span className="ml-2 text-xs text-tx3">wave 2</span>
                  ) : null}
                </button>
              </td>
              <td className="px-4 py-3 font-mono text-xs text-tx3">
                {row.archetype_id || row.template_id}
              </td>
              <td className="px-4 py-3 text-tx2">{row.section}</td>
              <td className="px-4 py-3">
                <CoverageStatusBadge status={row.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Templates() {
  const { brandId: rawBrandId, brandLabel } = useBrand()
  const brandId = rawBrandId || 'swing-shack'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [bibleOpen, setBibleOpen] = useState(true)
  const [view, setView] = useState<'catalog' | 'roadmap'>('catalog')
  const [selected, setSelected] = useState<TemplateGalleryTemplate | null>(null)
  const [gallery, setGallery] = useState<Awaited<ReturnType<typeof fetchTemplateGallery>> | null>(
    null,
  )

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    fetchTemplateGallery(brandId)
      .then((data) => {
        if (data.error && !data.templates?.length) {
          setError(data.error)
        }
        setGallery(data)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [brandId])

  useEffect(() => {
    load()
  }, [load])

  const bible = gallery?.brand_bible
  const coverage = gallery?.coverage
  const summary = coverage?.summary

  const statusById = useMemo(() => {
    const map = new Map<string, TemplateGalleryTemplate['status']>()
    for (const row of coverage?.rows || []) {
      const id = row.archetype_id || row.template_id
      if (id) map.set(id, row.status)
    }
    return map
  }, [coverage?.rows])

  const catalogSections = useMemo(() => {
    const templates = (gallery?.templates || []).map((t) => ({
      ...t,
      status: statusById.get(t.template_id) ?? ('ready' as const),
    }))
    const allowed = templates.filter(
      (t) => t.status === 'ready' || t.status === 'partial' || !t.status,
    )
    const bySec: Record<string, TemplateGalleryTemplate[]> = {}
    for (const t of allowed) {
      const sec = t.section || 'Other'
      bySec[sec] = bySec[sec] || []
      bySec[sec].push(t)
    }
    const order = [
      'Services',
      'Promo',
      'Brand',
      'Shop',
      'Coaching',
      'Location',
      'Education',
      'Other',
    ]
    const out: { section: string; templates: TemplateGalleryTemplate[] }[] = []
    const seen = new Set<string>()
    for (const sec of order) {
      if (bySec[sec]?.length) {
        out.push({ section: sec, templates: bySec[sec] })
        seen.add(sec)
      }
    }
    for (const [sec, rows] of Object.entries(bySec).sort(([a], [b]) => a.localeCompare(b))) {
      if (!seen.has(sec)) out.push({ section: sec, templates: rows })
    }
    return out
  }, [gallery?.templates, statusById])

  const roadmapRows = coverage?.rows || []

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Layers}
        badge="Compose layouts"
        here="/results/templates"
        title="Templates"
      >
        Brand bible and compose templates for {brandLabel || brandId}. Read-only reference for
        operators.
      </PageIntro>

      {loading ? (
        <div className="h-40 animate-pulse rounded-2xl bg-bg3" />
      ) : error ? (
        <p className="rounded-2xl border border-red/30 bg-red/5 px-4 py-3 text-sm text-red">
          {error}
        </p>
      ) : null}

      {!loading && summary ? (
        <CoverageSummaryBar
          ready={summary.ready}
          partial={summary.partial}
          missing={summary.missing}
        />
      ) : null}

      {!loading && bible ? (
        <section className="glass rounded-2xl border border-white/10">
          <button
            type="button"
            onClick={() => setBibleOpen((o) => !o)}
            className="flex w-full items-center justify-between gap-2 px-5 py-4 text-left"
          >
            <span className="font-display text-lg font-semibold">Brand bible</span>
            {bibleOpen ? (
              <ChevronUp className="h-5 w-5 text-tx3" />
            ) : (
              <ChevronDown className="h-5 w-5 text-tx3" />
            )}
          </button>
          {bibleOpen ? (
            <div className="space-y-4 border-t border-white/10 px-5 pb-5 pt-2">
              {bible.philosophy ? (
                <p className="text-sm text-tx2">{bible.philosophy}</p>
              ) : null}
              {bible.voice ? (
                <p className="text-sm italic text-tx3">{bible.voice}</p>
              ) : null}
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="text-sm font-semibold text-ac">Composition rules</h3>
                  <div className="mt-2">
                    <BulletList items={bible.composition_rules} empty="No rules listed." />
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-yel">Anti-patterns</h3>
                  <div className="mt-2">
                    <BulletList items={bible.anti_patterns} empty="No anti-patterns listed." />
                  </div>
                </div>
              </div>
              <PaletteSwatches rows={bible.palette_summary} />
            </div>
          ) : null}
        </section>
      ) : null}

      {!loading ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setView('catalog')}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${
              view === 'catalog'
                ? 'bg-ac text-bg'
                : 'border border-white/15 text-tx2 hover:bg-white/5'
            }`}
          >
            Catalog
          </button>
          <button
            type="button"
            onClick={() => setView('roadmap')}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${
              view === 'roadmap'
                ? 'bg-ac text-bg'
                : 'border border-white/15 text-tx2 hover:bg-white/5'
            }`}
          >
            Full roadmap
          </button>
        </div>
      ) : null}

      {!loading && view === 'catalog'
        ? catalogSections.map((sec) => (
            <section key={sec.section}>
              <h2 className="mb-3 font-display text-xl font-semibold">{sec.section}</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {sec.templates.map((t) => (
                  <TemplateCard key={t.template_id} template={t} onSelect={setSelected} />
                ))}
              </div>
            </section>
          ))
        : null}

      {!loading && view === 'roadmap' ? (
        <section>
          <h2 className="mb-3 font-display text-xl font-semibold">Service template roadmap</h2>
          <p className="mb-4 text-sm text-tx3">
            7×7 Content Bank families plus wave-2 extras. Click any row for detail — including
            gaps not yet on disk.
          </p>
          <RoadmapTable rows={roadmapRows} onSelect={setSelected} />
        </section>
      ) : null}

      {selected ? <DetailDrawer template={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  )
}
