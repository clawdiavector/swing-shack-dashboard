import { ChevronDown, ChevronUp, Layers } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrandScope } from '../components/BrandSwitch'
import { FilterChips, PageIntro } from '../components/chrome'
import { TemplateReferenceTag, templateMetaFromRecord } from '../components/TemplateReferenceTag'
import { Badge, ClassicLink, QueueItem, QueueItemThumb, Tip } from '../components/ui'
import {
  fetchBrandLibrary,
  resolveAssetUrl,
  type LibraryDraftRow,
  type LibraryPayload,
  type LibrarySandboxRow,
  type LibraryTemplateRow,
} from '../lib/api'
import { captionTag } from '../lib/captionPresence'
import { sandboxTitle } from '../lib/sandboxRow'
import { formatStamp } from '../lib/stamp'

const TAB_IDS = ['drafts', 'sandbox', 'templates'] as const
type TabId = (typeof TAB_IDS)[number]

function normalizeTab(raw: string | null): TabId {
  const v = String(raw || '').trim().toLowerCase()
  if (TAB_IDS.includes(v as TabId)) return v as TabId
  return 'drafts'
}

function statusTone(status?: string): 'gold' | 'green' | 'red' | 'mute' {
  const s = String(status || '').toLowerCase()
  if (s === 'dispatched' || s === 'approved') return 'green'
  if (s === 'failed' || s === 'rejected') return 'red'
  if (s === 'pending') return 'gold'
  return 'mute'
}

function DraftRowItem({ row }: { row: LibraryDraftRow }) {
  const cap = captionTag(row)
  const thumb = resolveAssetUrl(row.image_url || row.image_path || undefined)
  return (
    <QueueItem
      to={row.review_href || '/review'}
      layout="vertical"
      hideImageFallbackBadge={false}
      title={row.title || row.asset_id}
      stateBadge={row.status || 'pending'}
      channelBadge={row.primary_channel || row.platform || undefined}
      thumb={thumb || undefined}
      thumbAlt={row.title || row.asset_id}
      meta={row.caption ? row.caption.slice(0, 140) : 'No caption text stored'}
      stamp={row.updated_at || row.created_at}
      stampKind="updated"
      brandSlot={
        <>
          <Badge tone={cap.tone}>{cap.label}</Badge>
          {row.orphan ? <Badge tone="gold">Orphan</Badge> : null}
          {row.compose_pending ? <Badge tone="gold">Compose pending</Badge> : null}
          {!row.image_present ? <Badge tone="mute">No image</Badge> : null}
          <TemplateReferenceTag meta={templateMetaFromRecord(row)} preview="label-only" />
        </>
      }
      action={
        <Tip text="Open in Review — read-only inventory; approve and reject stay on Review.">
          <span className="text-xs font-semibold text-ac">Open in Review</span>
        </Tip>
      }
    />
  )
}

function SandboxRowItem({ row }: { row: LibrarySandboxRow }) {
  const cap = captionTag(row)
  const title = sandboxTitle(row as Parameters<typeof sandboxTitle>[0])
  const thumb = row.receipt_only ? undefined : resolveAssetUrl(row.image_url || undefined)
  return (
    <article className="glass space-y-2 rounded-2xl border border-white/10 p-4">
      <div className="flex flex-wrap items-start gap-3">
        {thumb ? (
          <QueueItemThumb src={thumb} alt={title} className="h-16 w-16 shrink-0 rounded-xl border border-bd object-cover" />
        ) : (
          <div className="grid h-16 w-16 shrink-0 place-items-center rounded-xl border border-dashed border-bd text-[10px] text-tx3">
            {row.receipt_only ? 'Receipt only' : 'No image'}
          </div>
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Link to={row.sandbox_href || '/publish'} className="font-semibold text-tx hover:text-ac">
              {title}
            </Link>
            <Badge tone={statusTone(row.status)}>{row.status || 'pending'}</Badge>
            <Badge tone={cap.tone}>{cap.label}</Badge>
            {row.human_approved ? <Badge tone="green">Approved ✓</Badge> : null}
            {row.receipt_only ? <Badge tone="gold">Receipt only</Badge> : null}
            {row.caption_truncated ? <Badge tone="mute">Caption truncated</Badge> : null}
          </div>
          {row.sandbox_post_id ? (
            <p className="text-xs text-tx3">
              Sandbox post {row.sandbox_post_id}
              {row.dispatched_at ? ` · dispatched ${formatStamp(row.dispatched_at)}` : ''}
            </p>
          ) : null}
          <details className="text-xs text-tx3">
            <summary className="cursor-pointer font-semibold text-tx2">Technical ids</summary>
            <ul className="mt-1 space-y-0.5 font-mono">
              {row.idempotency_key ? <li>idempotency_key: {row.idempotency_key}</li> : null}
              {row.queue_id ? <li>queue_id: {row.queue_id}</li> : null}
            </ul>
          </details>
          <Link to={row.sandbox_href || '/publish'} className="text-xs font-semibold text-ac">
            Open sandbox preview
          </Link>
        </div>
      </div>
    </article>
  )
}

function TemplateLibraryCard({ row }: { row: LibraryTemplateRow }) {
  const [open, setOpen] = useState(false)
  const cover = resolveAssetUrl(row.reference_images?.[0]?.url)
  const refCount = row.reference_images?.length ?? 0
  return (
    <article className="glass flex flex-col overflow-hidden rounded-2xl border border-white/10">
      <div className="relative aspect-[4/5] w-full bg-bg2">
        {cover ? (
          <QueueItemThumb
            src={cover}
            alt={row.template_label || row.template_id}
            className="h-full w-full rounded-none border-0 object-cover"
          />
        ) : (
          <div className="grid h-full place-items-center text-xs text-tx3">No preview</div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-tx">{row.template_label || row.template_id}</p>
          {row.section ? <Badge tone="mute">{row.section}</Badge> : null}
          <Badge tone="mute">{refCount} references</Badge>
        </div>
        <div className="flex flex-wrap gap-1">
          {row.canvas ? <Badge tone="mute">{row.canvas}</Badge> : null}
          <Badge tone={row.needs_photo ? 'gold' : 'green'}>
            {row.needs_photo ? 'Photo' : 'Compose only'}
          </Badge>
          {row.references_undeclared ? (
            <Badge tone="gold">references not declared in spec</Badge>
          ) : null}
        </div>
        {row.references_undeclared ? (
          <p className="text-xs text-tx3">
            The composer measured from nothing; these images are on disk only.
          </p>
        ) : null}
        <div className="mt-auto flex flex-wrap gap-2 pt-2">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-xs font-semibold text-ac"
          >
            {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {open ? 'Hide references' : 'Show references'}
          </button>
          <Link to={row.templates_href || '/results/templates'} className="text-xs font-semibold text-tx2 hover:text-ac">
            Full template spec
          </Link>
        </div>
        {open && refCount > 0 ? (
          <ul className="mt-2 flex flex-wrap gap-2">
            {(row.reference_images || []).map((ref) => {
              const url = resolveAssetUrl(ref.url)
              if (!url) return null
              return (
                <li key={ref.url} className="w-24 space-y-1">
                  <img src={url} alt="" className="aspect-square w-full rounded-lg border border-bd object-cover" />
                  <p className="text-[10px] text-tx3">
                    {ref.role === 'post' ? 'Latest post' : ref.role === 'golden' ? 'Template' : 'Measured ad'}
                  </p>
                </li>
              )
            })}
          </ul>
        ) : null}
      </div>
    </article>
  )
}

export function Library() {
  const { scope, isAll } = useBrandScope()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = normalizeTab(searchParams.get('tab'))
  const brandId = scope === 'all' ? 'swing-shack' : scope

  const [data, setData] = useState<LibraryPayload | null>(null)
  const [error, setError] = useState('')
  const [draftStatus, setDraftStatus] = useState('all')
  const [sandboxStatus, setSandboxStatus] = useState('all')
  const [captionFilter, setCaptionFilter] = useState('any')
  const [imageFilter, setImageFilter] = useState('any')

  useEffect(() => {
    const raw = searchParams.get('tab')
    const norm = normalizeTab(raw)
    if (raw !== norm) {
      setSearchParams({ tab: norm }, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const setTab = useCallback(
    (next: TabId) => {
      setSearchParams({ tab: next }, { replace: true })
    },
    [setSearchParams],
  )

  const load = useCallback(() => {
    if (isAll) {
      setError('Pick one brand — Library is per brand.')
      return
    }
    fetchBrandLibrary(brandId, { view: 'all' })
      .then((payload) => {
        setData(payload)
        setError(payload.error || '')
      })
      .catch((err: Error) => setError(err.message))
  }, [brandId, isAll])

  useEffect(() => {
    load()
  }, [load])

  const drafts = useMemo(() => {
    let rows = [...(data?.drafts || [])]
    if (draftStatus !== 'all') rows = rows.filter((r) => r.status === draftStatus)
    if (captionFilter === 'present') rows = rows.filter((r) => r.caption_present)
    if (captionFilter === 'absent') rows = rows.filter((r) => !r.caption_present)
    if (imageFilter === 'present') rows = rows.filter((r) => r.image_present)
    if (imageFilter === 'absent') rows = rows.filter((r) => !r.image_present)
    return rows
  }, [data?.drafts, draftStatus, captionFilter, imageFilter])

  const sandbox = useMemo(() => {
    let rows = [...(data?.sandbox || [])]
    if (sandboxStatus !== 'all') rows = rows.filter((r) => r.status === sandboxStatus)
    if (captionFilter === 'present') rows = rows.filter((r) => r.caption_present)
    if (captionFilter === 'absent') rows = rows.filter((r) => !r.caption_present)
    return rows
  }, [data?.sandbox, sandboxStatus, captionFilter])

  const templates = data?.templates || []
  const templatesBySection = useMemo(() => {
    const map = new Map<string, LibraryTemplateRow[]>()
    for (const row of templates) {
      const sec = row.section || 'Other'
      map.set(sec, [...(map.get(sec) || []), row])
    }
    return map
  }, [templates])

  const counts = data?.counts

  const headerLine =
    tab === 'drafts'
      ? `${counts?.drafts?.returned ?? drafts.length} drafts · ${counts?.drafts?.with_caption ?? 0} with caption · ${counts?.drafts?.with_image ?? 0} with image`
      : tab === 'sandbox'
        ? `${counts?.sandbox?.returned ?? sandbox.length} items · ${counts?.sandbox?.with_caption ?? 0} with caption · ${counts?.sandbox?.without_caption ?? 0} without`
        : `${counts?.templates?.returned ?? templates.length} templates · ${counts?.templates?.reference_images ?? 0} reference images`

  return (
    <div className="space-y-6">
      <PageIntro icon={Layers} here="/library" title="Library">
        Read-only inventory of draft assets, sandbox posts, and template reference art for this brand.
        Nothing here deletes, archives, or dispatches — use Review and Publish to act.{' '}
        <ClassicLink href="/visualizer" label="Classic visual library" />
      </PageIntro>

      {isAll ? (
        <p className="rounded-2xl border border-yel/40 bg-yel/10 px-4 py-3 text-sm text-yel">
          Select a single brand to load the library shelves.
        </p>
      ) : null}

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
      ) : null}

      <FilterChips
        value={tab}
        onChange={(id) => setTab(normalizeTab(id))}
        options={[
          { id: 'drafts', label: 'Drafts' },
          { id: 'sandbox', label: 'Sandbox posts' },
          { id: 'templates', label: 'Templates' },
        ]}
      />

      <p className="text-sm text-tx2">{headerLine}</p>

      {tab === 'sandbox' ? (
        <p className="text-xs text-tx3">
          Sandbox / mock — not live. Rows mirror the publish sandbox queue and receipts; dispatch stays on Publish.
        </p>
      ) : null}

      {(tab === 'drafts' || tab === 'sandbox') && (
        <FilterChips
          value={captionFilter}
          onChange={setCaptionFilter}
          options={[
            { id: 'any', label: 'Caption: any' },
            { id: 'present', label: 'Caption: present' },
            { id: 'absent', label: 'Caption: absent' },
          ]}
        />
      )}

      {tab === 'drafts' ? (
        <>
          <FilterChips
            value={draftStatus}
            onChange={setDraftStatus}
            options={[
              { id: 'all', label: 'All' },
              { id: 'pending', label: 'Pending' },
              { id: 'approved', label: 'Approved' },
              { id: 'rejected', label: 'Rejected' },
              { id: 'archived', label: 'Archived' },
            ]}
          />
          <FilterChips
            value={imageFilter}
            onChange={setImageFilter}
            options={[
              { id: 'any', label: 'Image: any' },
              { id: 'present', label: 'Image: present' },
              { id: 'absent', label: 'Image: absent' },
            ]}
          />
          <div className="space-y-3">
            {drafts.length === 0 ? (
              <p className="text-sm text-tx3">No draft assets for this brand yet.</p>
            ) : (
              drafts.map((row) => <DraftRowItem key={row.asset_id} row={row} />)
            )}
          </div>
        </>
      ) : null}

      {tab === 'sandbox' ? (
        <>
          <FilterChips
            value={sandboxStatus}
            onChange={setSandboxStatus}
            options={[
              { id: 'all', label: 'All' },
              { id: 'pending', label: 'Pending' },
              { id: 'dispatched', label: 'Dispatched' },
              { id: 'failed', label: 'Failed' },
            ]}
          />
          <div className="space-y-3">
            {sandbox.length === 0 ? (
              <p className="text-sm text-tx3">No sandbox queue rows for this brand.</p>
            ) : (
              sandbox.map((row) => (
                <SandboxRowItem key={String(row.idempotency_key || row.queue_id || row.sandbox_post_id)} row={row} />
              ))
            )}
          </div>
        </>
      ) : null}

      {tab === 'templates' ? (
        templates.length === 0 ? (
          <p className="text-sm text-tx3">
            No compose templates for this brand yet — add template packs under brand directory when ready.
          </p>
        ) : (
          <div className="space-y-8">
            {[...templatesBySection.entries()].map(([section, rows]) => (
              <section key={section}>
                <h2 className="mb-3 font-display text-lg font-semibold">{section}</h2>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {rows.map((row) => (
                    <TemplateLibraryCard key={row.template_id} row={row} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )
      ) : null}
    </div>
  )
}
