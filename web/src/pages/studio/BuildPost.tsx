import { Hammer, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../../components/chrome'
import { Badge, Button, ClassicLink, Tip } from '../../components/ui'
import {
  fetchAssetAiDraft,
  fetchInboxItem,
  postJson,
  type InboxItem,
} from '../../lib/api'
import { parentLabel } from '../../lib/tools'

type PreflightStage = {
  passed?: boolean
  total?: number
  passed_count?: number
  failed_count?: number
  applicable?: boolean
  checks?: { passed?: boolean; name?: string }[]
}

type BuildPostPackage = {
  final_status?: string
  status?: string
  store_brand?: string
  brand_id?: string
  product_brand?: string
  product?: { name?: string; id?: string }
  reference_verified?: boolean
  pricing_text?: string
  pricing_currency?: string
  krea_required?: boolean
  krea_status?: string
  krea_model?: string
  krea_job_id?: string
  draft_quality?: PreflightStage
  publish_preflight?: PreflightStage
  preflight?: PreflightStage
  blocked_reasons?: { check?: string; message?: string }[]
  human_brief?: unknown
  saved_path?: string
  asset_id?: string
}

type DraftResponse = { ok?: boolean; package?: BuildPostPackage; error?: string }

type SlotResponse = {
  ok?: boolean
  recommended?: { time?: string; reason?: string; confidence?: string }
  disclaimer?: string
}

type QueuePreview = {
  ok?: boolean
  breakdown?: {
    selected?: number
    pass?: unknown[]
    blocked?: { product?: string; asset_id?: string; reason?: string }[]
  }
  error?: string
}

type QueueConfirm = {
  ok?: boolean
  queued?: unknown[]
  queue_failed?: unknown[]
  error?: string
}

function statusTone(status: string): 'green' | 'gold' | 'red' | 'mute' {
  const s = status.toUpperCase()
  if (s === 'DRAFT_READY') return 'green'
  if (s === 'BLOCKED') return 'red'
  if (s === 'DRAFT_HAS_NOTES' || s === 'NEEDS_APPROVAL' || s === 'NEEDS_CAPTURE') return 'gold'
  return 'mute'
}

function resolveAssetIds(pkg: BuildPostPackage | null, urlAsset?: string | null): string[] {
  if (urlAsset) return [urlAsset]
  if (pkg?.asset_id) return [pkg.asset_id]
  if (pkg?.saved_path) {
    const fn = pkg.saved_path.split('/').pop() || ''
    const stub = fn.replace(/\.[^.]+$/, '')
    if (stub) return [stub]
  }
  return []
}

function Field({
  label,
  tip,
  children,
}: {
  label: string
  tip: string
  children: ReactNode
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-semibold tracking-wide text-tx3 uppercase">
        <Tip text={tip}>{label}</Tip>
      </span>
      {children}
    </label>
  )
}

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx placeholder:text-tx3 focus:border-ac focus:outline-none'

export function BuildPost() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params] = useSearchParams()

  const itemId = params.get('item')
  const assetParam = params.get('asset')
  const campaignParam = params.get('campaign')
  const titleParam = params.get('title')
  const from = params.get('from') || '/create'

  const [lane, setLane] = useState('product')
  const [productBrand, setProductBrand] = useState('')
  const [productId, setProductId] = useState('')
  const [calendarItemId, setCalendarItemId] = useState('')
  const [ideaText, setIdeaText] = useState('')
  const [hook, setHook] = useState('')
  const [campaignId, setCampaignId] = useState(campaignParam || '')

  const [inboxMeta, setInboxMeta] = useState<InboxItem | null>(null)
  const [prefillNote, setPrefillNote] = useState('')

  const [pkg, setPkg] = useState<BuildPostPackage | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const [slot, setSlot] = useState<SlotResponse | null>(null)
  const [queuePreview, setQueuePreview] = useState<QueuePreview | null>(null)
  const [queueConfirm, setQueueConfirm] = useState<QueueConfirm | null>(null)
  const [queueBusy, setQueueBusy] = useState(false)

  useEffect(() => {
    if (!scopeBrand) return
    fetch(`/api/build-post/recommended-slot?brand_id=${encodeURIComponent(scopeBrand)}&channel=instagram`, {
      credentials: 'same-origin',
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setSlot(data as SlotResponse))
      .catch(() => setSlot(null))
  }, [scopeBrand])

  useEffect(() => {
    let cancelled = false
    async function prefill() {
      let resolvedCampaign = campaignParam || ''
      let resolvedAsset = assetParam || ''
      if (titleParam) setIdeaText((prev) => prev || titleParam)
      if (itemId) {
        const item = await fetchInboxItem(itemId)
        if (cancelled) return
        if (item) {
          setInboxMeta(item)
          if (item.meta?.campaign_id) resolvedCampaign = item.meta.campaign_id
          setCampaignId((prev) => prev || item.meta?.campaign_id || '')
          if (item.title) setIdeaText((prev) => prev || item.title || '')
          if (item.summary) setHook((prev) => prev || item.summary?.slice(0, 200) || '')
          if (item.meta?.asset_id) resolvedAsset = resolvedAsset || item.meta.asset_id
        }
      }
      if (resolvedAsset) {
        try {
          const draft = await fetchAssetAiDraft(resolvedAsset, resolvedCampaign || undefined)
          if (cancelled) return
          if (draft.caption) {
            setIdeaText((prev) => prev || draft.caption || '')
            setPrefillNote(
              'Prefilled from asset AI draft — classic ignored URL params; this fixes that hop.',
            )
          }
          if (draft.campaignId) setCampaignId((prev) => prev || draft.campaignId || '')
        } catch {
          /* 404 — no draft */
        }
      }
    }
    prefill()
    return () => {
      cancelled = true
    }
  }, [itemId, assetParam, campaignParam, titleParam])

  const packageStatus = useMemo(() => {
    if (!pkg) return ''
    return (pkg.final_status || pkg.status || 'UNKNOWN').toUpperCase()
  }, [pkg])

  const handleBuild = useCallback(async () => {
    if (!scopeBrand) return
    setBusy(true)
    setError('')
    setQueuePreview(null)
    setQueueConfirm(null)
    try {
      const body: Record<string, string> = {
        brand_id: scopeBrand,
        lane,
        idea_text: ideaText,
        hook,
      }
      if (calendarItemId) body.calendar_item_id = calendarItemId
      if (productBrand) body.product_brand = productBrand
      if (productId) body.product_id = productId
      if (campaignId) body.campaign_id = campaignId
      const res = await postJson<DraftResponse>('/api/build-post/draft', body)
      if (!res.ok) {
        setError(res.error || 'Build failed')
        setPkg(null)
        return
      }
      setPkg(res.package || null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Build failed')
      setPkg(null)
    } finally {
      setBusy(false)
    }
  }, [
    scopeBrand,
    lane,
    ideaText,
    hook,
    calendarItemId,
    productBrand,
    productId,
    campaignId,
  ])

  const assetIds = useMemo(
    () => resolveAssetIds(pkg, assetParam),
    [pkg, assetParam],
  )

  const handlePreviewQueue = useCallback(async () => {
    if (!scopeBrand || assetIds.length === 0) {
      setError('No asset id — build a draft first or arrive with ?asset=')
      return
    }
    setQueueBusy(true)
    setQueueConfirm(null)
    try {
      const res = await postJson<QueuePreview>('/api/build-post/approve-queue', {
        brand_id: scopeBrand,
        asset_ids: assetIds,
        confirmed: false,
      })
      setQueuePreview(res)
      if (!res.ok) setError(res.error || 'Preview failed')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Preview failed')
    } finally {
      setQueueBusy(false)
    }
  }, [scopeBrand, assetIds])

  const handleConfirmQueue = useCallback(async () => {
    if (!scopeBrand || assetIds.length === 0) return
    setQueueBusy(true)
    try {
      const res = await postJson<QueueConfirm>('/api/build-post/approve-queue', {
        brand_id: scopeBrand,
        asset_ids: assetIds,
        confirmed: true,
      })
      setQueueConfirm(res)
      if (!res.ok) setError(res.error || 'Queue failed')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Queue failed')
    } finally {
      setQueueBusy(false)
    }
  }, [scopeBrand, assetIds])

  const usingStubId =
    pkg?.saved_path && !pkg.asset_id && !assetParam && assetIds.length > 0

  return (
    <div className="space-y-6">
      <PageIntro
        here="/create"
        title="Build a post"
        actions={
          from ? (
            <Button to={from} tone="ghost" tip={`Back to ${parentLabel(from)}.`}>
              Back
            </Button>
          ) : null
        }
      >
        One click assembles a draft package; preview then confirm queues via with-gate. No auto-publish.
        {prefillNote ? ` ${prefillNote}` : ''}
        <span className="mt-2 block">
          <ClassicLink href="/?page=buildpost" label="Build a post" />
        </span>
      </PageIntro>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <HeroPanel
          icon={Hammer}
          kicker="Studio"
          title="Draft inputs"
          meta={scopeBrand ? `Brand: ${scopeBrand}` : 'Pick a brand in the rail'}
        >
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Lane" tip="Product vs editorial lane for the builder.">
              <select className={inputCls} value={lane} onChange={(e) => setLane(e.target.value)}>
                <option value="product">Product</option>
                <option value="editorial">Editorial</option>
                <option value="evergreen">Evergreen</option>
              </select>
            </Field>
            <Field label="Calendar item id" tip="Optional calendar row to attach this draft.">
              <input
                className={inputCls}
                value={calendarItemId}
                onChange={(e) => setCalendarItemId(e.target.value)}
                placeholder="calendar_item_id"
              />
            </Field>
            <Field label="Product brand" tip="Visual/product brand when different from store voice.">
              <input
                className={inputCls}
                value={productBrand}
                onChange={(e) => setProductBrand(e.target.value)}
              />
            </Field>
            <Field label="Product id" tip="Catalog product id for verified reference.">
              <input className={inputCls} value={productId} onChange={(e) => setProductId(e.target.value)} />
            </Field>
          </div>
          <Field label="Idea" tip="Core idea or caption seed — prefilled from review hop when present.">
            <textarea
              className={`${inputCls} min-h-[88px]`}
              value={ideaText}
              onChange={(e) => setIdeaText(e.target.value)}
            />
          </Field>
          <Field label="Hook" tip="Opening hook line for the post package.">
            <input className={inputCls} value={hook} onChange={(e) => setHook(e.target.value)} />
          </Field>
          {campaignId ? (
            <p className="text-xs text-tx3">
              Campaign id (from inbox/asset): <span className="font-mono text-tx2">{campaignId}</span>
            </p>
          ) : null}
          {itemId ? (
            <p className="text-xs text-tx3">
              Inbox item:{' '}
              <Link to={`/review/${encodeURIComponent(itemId)}`} className="text-ac hover:text-yel">
                {itemId}
              </Link>
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Tip text="POST /api/build-post/draft — assemble the full package.">
              <button
                type="button"
                disabled={busy || !scopeBrand}
                onClick={handleBuild}
                className="inline-flex items-center gap-1.5 rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-50"
              >
                <Sparkles className="h-4 w-4" strokeWidth={2.5} />
                {busy ? 'Building…' : 'Build post'}
              </button>
            </Tip>
          </div>
          {error ? <p className="mt-2 text-sm text-red">{error}</p> : null}
        </HeroPanel>

        <aside className="space-y-4">
          <section className="glass rounded-2xl border border-white/10 p-4">
            <h2 className="text-sm font-semibold">Recommended slot</h2>
            <p className="mt-1 text-xs text-tx3">Not optimal — heuristic only.</p>
            {slot?.ok && slot.recommended ? (
              <div className="mt-3 space-y-1 text-sm">
                <p>
                  <span className="font-semibold">Instagram:</span> {slot.recommended.time || '?'} ·{' '}
                  {slot.recommended.reason || ''}
                </p>
                <p className="text-xs text-tx3">
                  confidence: <b>{slot.recommended.confidence || 'unknown'}</b>
                </p>
                {slot.disclaimer ? <p className="text-xs text-tx3">{slot.disclaimer}</p> : null}
              </div>
            ) : (
              <p className="mt-2 text-sm text-tx3">Load a brand to see slot hint.</p>
            )}
          </section>
        </aside>
      </div>

      {pkg ? (
        <section className="glass space-y-4 rounded-2xl border border-white/10 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-xl font-semibold">Draft package</h2>
            {packageStatus ? (
              <Badge tone={statusTone(packageStatus)}>{packageStatus}</Badge>
            ) : null}
          </div>
          <div className="grid gap-2 text-sm text-tx2">
            <p>
              <b>Store brand:</b> {pkg.store_brand || pkg.brand_id || '—'}
            </p>
            {pkg.product_brand && pkg.product_brand !== pkg.store_brand ? (
              <p>
                <b>Product brand:</b> {pkg.product_brand}
              </p>
            ) : null}
            {pkg.product ? (
              <p>
                <b>Product:</b> {pkg.product.name || '?'} ({pkg.product.id || '?'})
              </p>
            ) : null}
            {pkg.product ? (
              <p>
                <b>Reference verified:</b>{' '}
                {pkg.reference_verified ? (
                  <span className="text-ac">YES</span>
                ) : (
                  <span className="text-red">NO</span>
                )}
              </p>
            ) : null}
            {pkg.pricing_text ? (
              <p>
                <b>Pricing:</b> {pkg.pricing_text}{' '}
                {pkg.pricing_currency ? `(${pkg.pricing_currency})` : ''}
              </p>
            ) : null}
            <p>
              <b>Krea:</b>{' '}
              {pkg.krea_required
                ? `${pkg.krea_status || 'unknown'}${pkg.krea_model ? ` · ${pkg.krea_model}` : ''}`
                : 'not required for this lane'}
            </p>
            {pkg.draft_quality && pkg.draft_quality.applicable !== false ? (
              <p>
                <b>Draft quality:</b> {pkg.draft_quality.passed_count}/{pkg.draft_quality.total}
              </p>
            ) : null}
            {pkg.publish_preflight && pkg.publish_preflight.applicable !== false ? (
              <p>
                <b>Publish preflight:</b> {pkg.publish_preflight.passed_count}/
                {pkg.publish_preflight.total}
              </p>
            ) : null}
            {pkg.human_brief ? <p className="text-tx3">Human brief included in package.</p> : null}
          </div>
          {(pkg.blocked_reasons || []).length > 0 ? (
            <ul className="space-y-2">
              {(pkg.blocked_reasons || []).map((b, i) => (
                <li
                  key={i}
                  className="rounded-xl border-l-4 border-red bg-bg2/80 px-3 py-2 text-sm"
                >
                  <b>{b.check}</b> — {b.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ac">No blockers listed.</p>
          )}
          {usingStubId ? (
            <p className="rounded-xl border border-yel/30 bg-yel/5 px-3 py-2 text-xs text-yel">
              Queue preview uses saved_path basename as asset id stub — prefer ?asset= or package
              asset_id when available.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-2">
            <Tip text="Preview queue breakdown without publishing (confirmed: false).">
              <button
                type="button"
                disabled={queueBusy || assetIds.length === 0}
                onClick={handlePreviewQueue}
                className="rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50"
              >
                Preview queue
              </button>
            </Tip>
            {queuePreview?.ok ? (
              <Tip text="Second click — confirmed:true queues via with-gate. No auto-publish before this.">
                <button
                  type="button"
                  disabled={queueBusy}
                  onClick={handleConfirmQueue}
                  className="rounded-full bg-ac px-4 py-2 text-sm font-semibold text-bg hover:bg-ac/90 disabled:opacity-50"
                >
                  Confirm queue
                </button>
              </Tip>
            ) : null}
          </div>
          {queuePreview?.breakdown ? (
            <div className="rounded-xl bg-bg2/80 p-3 text-sm">
              <p>{queuePreview.breakdown.selected ?? 0} selected</p>
              <p className="text-ac">{(queuePreview.breakdown.pass || []).length} pass preflight</p>
              <p className="text-red">{(queuePreview.breakdown.blocked || []).length} blocked</p>
              {(queuePreview.breakdown.blocked || []).map((b, i) => (
                <p key={i} className="mt-1 text-xs text-tx3">
                  {b.product || b.asset_id}: {b.reason}
                </p>
              ))}
            </div>
          ) : null}
          {queueConfirm?.ok ? (
            <p className="text-sm text-ac">
              Queued {(queueConfirm.queued || []).length}; failed{' '}
              {(queueConfirm.queue_failed || []).length}.
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
