import { ChevronDown, ChevronUp, Layers, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrandScope } from '../components/BrandSwitch'
import { FilterChips, PageIntro } from '../components/chrome'
import { TemplateReferenceTag, templateMetaFromRecord } from '../components/TemplateReferenceTag'
import { Badge, ClassicLink, QueueItem, QueueItemThumb, Tip } from '../components/ui'
import {
  fetchBrandLibrary,
  postBrandLibraryBulk,
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

function draftRowKey(row: LibraryDraftRow): string {
  return String(row.asset_id || '')
}

function sandboxRowKey(row: LibrarySandboxRow): string {
  return String(row.idempotency_key || row.queue_id || '')
}

function isSandboxSelectable(row: LibrarySandboxRow): boolean {
  return !row.receipt_only && Boolean(row.queue_id)
}

/** Min 44px hit target — raw checkboxes are too small on touch / dense lists. */
function RowSelectCheckbox({
  checked,
  disabled,
  onToggle,
  ariaLabel,
}: {
  checked: boolean
  disabled?: boolean
  onToggle: () => void
  ariaLabel: string
}) {
  return (
    <label
      className={`inline-flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-center self-center rounded-xl hover:bg-white/5 active:bg-white/10 ${
        disabled ? 'cursor-not-allowed opacity-40 hover:bg-transparent' : ''
      }`}
    >
      <input
        type="checkbox"
        className="h-5 w-5 accent-ac"
        checked={checked}
        disabled={disabled}
        onChange={onToggle}
        aria-label={ariaLabel}
      />
    </label>
  )
}

type BulkConfirmState = {
  action: 'archive' | 'delete'
  lane: 'drafts' | 'sandbox'
  ids: string[]
  titles: string[]
  protectedCount: number
}

function BulkConfirmModal({
  state,
  includeApproved,
  onIncludeApproved,
  busy,
  onCancel,
  onConfirm,
}: {
  state: BulkConfirmState
  includeApproved: boolean
  onIncludeApproved: (v: boolean) => void
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const verb = state.action === 'archive' ? 'Archive' : 'Delete'
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal
      aria-label={`Confirm ${verb.toLowerCase()}`}
    >
      <div className="glass max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/15 p-5 shadow-2xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="font-display text-lg font-semibold">
            {verb} {state.ids.length} {state.lane === 'drafts' ? 'draft' : 'sandbox'} row
            {state.ids.length === 1 ? '' : 's'}?
          </h2>
          <button type="button" onClick={onCancel} className="rounded-lg p-2 hover:bg-white/10" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        {state.protectedCount > 0 ? (
          <p className="mb-2 text-sm text-yel">
            {state.protectedCount} selected row{state.protectedCount === 1 ? '' : 's'} will be skipped (approved,
            dispatched, or receipt-only).
          </p>
        ) : null}
        {state.action === 'delete' ? (
          <label className="mb-3 flex min-h-11 cursor-pointer items-center gap-3 rounded-xl py-1 text-sm text-tx2 hover:bg-white/5">
            <input
              type="checkbox"
              className="h-5 w-5 shrink-0 accent-ac"
              checked={includeApproved}
              onChange={(e) => onIncludeApproved(e.target.checked)}
            />
            Include human-approved / dispatched rows in delete
          </label>
        ) : null}
        <ul className="mb-4 max-h-48 space-y-1 overflow-y-auto text-sm text-tx2">
          {state.titles.slice(0, 12).map((t, i) => (
            <li key={`${t}-${i}`} className="truncate">
              · {t || state.ids[i] || 'Untitled'}
            </li>
          ))}
          {state.titles.length > 12 ? (
            <li className="text-tx3">…and {state.titles.length - 12} more</li>
          ) : null}
        </ul>
        <p className="mb-4 text-xs text-tx3">
          {state.action === 'delete' && state.lane === 'drafts'
            ? 'Draft delete removes the sidecar and campaign asset only — calendar moments on Planning stay.'
            : state.action === 'delete'
              ? 'Sandbox delete removes the queue row only; receipt history is unchanged.'
              : 'Archive hides rows from the default library list; you can still filter to archived.'}
        </p>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-xl border border-bd px-4 py-2 text-sm font-semibold text-tx2 hover:bg-white/5"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy || state.ids.length === 0}
            className="rounded-xl bg-ac px-4 py-2 text-sm font-semibold text-bg hover:opacity-90 disabled:opacity-50"
          >
            {busy ? 'Working…' : `${verb} ${state.ids.length}`}
          </button>
        </div>
      </div>
    </div>
  )
}

function DraftRowItem({
  row,
  selected,
  onToggle,
}: {
  row: LibraryDraftRow
  selected: boolean
  onToggle: () => void
}) {
  const cap = captionTag(row)
  const thumb = resolveAssetUrl(row.image_url || row.image_path || undefined)
  return (
    <div className="flex items-start gap-1 sm:gap-2">
      <RowSelectCheckbox
        checked={selected}
        onToggle={onToggle}
        ariaLabel={`Select ${row.title || row.asset_id}`}
      />
      <div className="min-w-0 flex-1">
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
        <Tip text="Open in Review for approve/reject; bulk archive/delete uses the toolbar above.">
          <span className="text-xs font-semibold text-ac">Open in Review</span>
        </Tip>
      }
    />
      </div>
    </div>
  )
}

function SandboxRowItem({
  row,
  selected,
  onToggle,
  selectable,
}: {
  row: LibrarySandboxRow
  selected: boolean
  onToggle: () => void
  selectable: boolean
}) {
  const cap = captionTag(row)
  const title = sandboxTitle(row as Parameters<typeof sandboxTitle>[0])
  const thumb = row.receipt_only ? undefined : resolveAssetUrl(row.image_url || undefined)
  return (
    <article className="glass space-y-2 rounded-2xl border border-white/10 p-4">
      <div className="flex flex-wrap items-start gap-1 sm:gap-2">
        <RowSelectCheckbox
          checked={selected}
          disabled={!selectable}
          onToggle={onToggle}
          ariaLabel={selectable ? `Select ${title}` : 'Receipt-only — not bulk-editable'}
        />
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
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkErr, setBulkErr] = useState('')
  const [confirm, setConfirm] = useState<BulkConfirmState | null>(null)
  const [includeApprovedDelete, setIncludeApprovedDelete] = useState(false)

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

  useEffect(() => {
    setSelected(new Set())
    setConfirm(null)
    setBulkErr('')
  }, [tab, brandId, draftStatus, sandboxStatus, captionFilter, imageFilter])

  const drafts = useMemo(() => {
    let rows = [...(data?.drafts || [])]
    if (draftStatus === 'all') rows = rows.filter((r) => r.status !== 'archived')
    else if (draftStatus !== 'all') rows = rows.filter((r) => r.status === draftStatus)
    if (captionFilter === 'present') rows = rows.filter((r) => r.caption_present)
    if (captionFilter === 'absent') rows = rows.filter((r) => !r.caption_present)
    if (imageFilter === 'present') rows = rows.filter((r) => r.image_present)
    if (imageFilter === 'absent') rows = rows.filter((r) => !r.image_present)
    return rows
  }, [data?.drafts, draftStatus, captionFilter, imageFilter])

  const sandbox = useMemo(() => {
    let rows = [...(data?.sandbox || [])]
    if (sandboxStatus === 'all') rows = rows.filter((r) => r.status !== 'archived')
    else if (sandboxStatus !== 'all') rows = rows.filter((r) => r.status === sandboxStatus)
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

  const visibleKeys = useMemo(() => {
    if (tab === 'drafts') return drafts.map((r) => draftRowKey(r)).filter(Boolean)
    if (tab === 'sandbox') return sandbox.filter(isSandboxSelectable).map((r) => sandboxRowKey(r)).filter(Boolean)
    return []
  }, [tab, drafts, sandbox])

  const toggleKey = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const selectAllVisible = useCallback(() => {
    setSelected(new Set(visibleKeys))
  }, [visibleKeys])

  const clearSelection = useCallback(() => setSelected(new Set()), [])

  const openBulkConfirm = useCallback(
    (action: 'archive' | 'delete') => {
      const lane = tab === 'sandbox' ? 'sandbox' : 'drafts'
      const ids = [...selected].filter((id) => visibleKeys.includes(id))
      const titles =
        lane === 'drafts'
          ? drafts.filter((r) => ids.includes(draftRowKey(r))).map((r) => r.title || r.asset_id || '')
          : sandbox
              .filter((r) => ids.includes(sandboxRowKey(r)))
              .map((r) => sandboxTitle(r as Parameters<typeof sandboxTitle>[0]))
      let protectedCount = 0
      if (lane === 'sandbox') {
        for (const r of sandbox) {
          const k = sandboxRowKey(r)
          if (!ids.includes(k)) continue
          if (r.receipt_only || (r.human_approved && !includeApprovedDelete) || (r.status === 'dispatched' && !includeApprovedDelete)) {
            protectedCount += 1
          }
        }
      } else if (action === 'delete') {
        protectedCount = drafts.filter(
          (r) => ids.includes(draftRowKey(r)) && r.status === 'approved' && !includeApprovedDelete,
        ).length
      }
      setConfirm({ action, lane, ids, titles, protectedCount })
    },
    [tab, selected, visibleKeys, drafts, sandbox, includeApprovedDelete],
  )

  const runBulk = useCallback(async () => {
    if (!confirm || isAll) return
    setBulkBusy(true)
    setBulkErr('')
    try {
      const res = await postBrandLibraryBulk(brandId, {
        lane: confirm.lane,
        action: confirm.action,
        ids: confirm.ids,
        include_approved: confirm.action === 'delete' ? includeApprovedDelete : undefined,
      })
      if (!res.ok) throw new Error(res.error || 'Bulk action failed')
      setConfirm(null)
      setSelected(new Set())
      load()
    } catch (e) {
      setBulkErr(e instanceof Error ? e.message : 'Bulk action failed')
    } finally {
      setBulkBusy(false)
    }
  }, [confirm, isAll, brandId, includeApprovedDelete, load])

  return (
    <div className="space-y-6">
      <PageIntro icon={Layers} here="/library" title="Library">
        Draft and sandbox inventory for this brand — multi-select on Drafts and Sandbox tabs to archive or delete
        junk rows. Calendar moments survive draft delete; receipt-only sandbox rows cannot be selected. Templates stay
        read-only.{' '}
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

      {bulkErr ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{bulkErr}</p>
      ) : null}

      {(tab === 'drafts' || tab === 'sandbox') && !isAll ? (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2">
          <span className="text-sm text-tx2">
            {selected.size} selected · {visibleKeys.length} visible
          </span>
          <button
            type="button"
            onClick={selectAllVisible}
            disabled={visibleKeys.length === 0}
            className="text-xs font-semibold text-ac disabled:opacity-40"
          >
            Select visible
          </button>
          <button
            type="button"
            onClick={clearSelection}
            disabled={selected.size === 0}
            className="text-xs font-semibold text-tx3 disabled:opacity-40"
          >
            Clear
          </button>
          <span className="mx-1 text-tx3">|</span>
          <button
            type="button"
            onClick={() => openBulkConfirm('archive')}
            disabled={selected.size === 0 || bulkBusy}
            className="rounded-lg border border-bd px-3 py-1 text-xs font-semibold text-tx hover:border-ac"
          >
            Archive
          </button>
          <button
            type="button"
            onClick={() => openBulkConfirm('delete')}
            disabled={selected.size === 0 || bulkBusy}
            className="rounded-lg border border-red/50 px-3 py-1 text-xs font-semibold text-red hover:bg-red/10"
          >
            Delete
          </button>
        </div>
      ) : null}

      {confirm ? (
        <BulkConfirmModal
          state={confirm}
          includeApproved={includeApprovedDelete}
          onIncludeApproved={setIncludeApprovedDelete}
          busy={bulkBusy}
          onCancel={() => setConfirm(null)}
          onConfirm={runBulk}
        />
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
              { id: 'archived', label: 'Archived only' },
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
              drafts.map((row) => {
                const key = draftRowKey(row)
                return (
                  <DraftRowItem
                    key={row.asset_id}
                    row={row}
                    selected={selected.has(key)}
                    onToggle={() => toggleKey(key)}
                  />
                )
              })
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
              { id: 'archived', label: 'Archived only' },
            ]}
          />
          <div className="space-y-3">
            {sandbox.length === 0 ? (
              <p className="text-sm text-tx3">No sandbox queue rows for this brand.</p>
            ) : (
              sandbox.map((row) => {
                const key = sandboxRowKey(row)
                return (
                  <SandboxRowItem
                    key={String(row.idempotency_key || row.queue_id || row.sandbox_post_id)}
                    row={row}
                    selectable={isSandboxSelectable(row)}
                    selected={selected.has(key)}
                    onToggle={() => toggleKey(key)}
                  />
                )
              })
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
