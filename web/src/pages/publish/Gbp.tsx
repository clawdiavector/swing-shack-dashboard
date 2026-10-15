import { MapPin } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink, Tip } from '../../components/ui'

const actionBtn =
  'rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50'
const primaryBtn = 'rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-50'
import {
  createGmbDraft,
  deleteGmbDraft,
  fetchGbpLatestPlan,
  fetchGbpPlans,
  fetchGbpStatus,
  fetchGbpSuggestions,
  fetchGmbDrafts,
  fetchGmbSearchTerms,
  approveGmbDraft,
  previewGbpDailyPlan,
  unapproveGmbDraft,
  uploadGmbDraftPhoto,
  scheduleGmbDraft,
  updateGmbDraft,
  type GmbDraft,
  type GmbSearchTerms,
  type GbpPlan,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'

type GbpTab = 'plans' | 'suggestions' | 'drafts'

const TAB_OPTIONS = [
  { id: 'plans', label: 'Plans' },
  { id: 'suggestions', label: 'Suggestions' },
  { id: 'drafts', label: 'Drafts' },
]

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

function resolveTab(raw: string | null): GbpTab {
  if (raw === 'suggestions' || raw === 'drafts') return raw
  return 'plans'
}

function BrandLiveConfirm({
  brandId,
  label,
  onConfirm,
  onCancel,
}: {
  brandId: string
  label: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const [typed, setTyped] = useState('')
  return (
    <div className="rounded-2xl border border-red/40 bg-red/5 p-4 text-sm">
      <p className="font-semibold text-tx">{label}</p>
      <p className="mt-2 text-tx2">
        Type <span className="font-mono text-yel">{brandId}</span> to confirm live publish for this brand.
      </p>
      <input
        className={`${inputCls} mt-3`}
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        aria-label="Confirm brand id"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={primaryBtn} disabled={typed !== brandId} onClick={onConfirm}>
          Confirm
        </button>
        <button type="button" className={actionBtn} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

export function Gbp() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? 'swing-shack'
  const [params, setParams] = useSearchParams()
  const tab = resolveTab(params.get('tab'))
  const [status, setStatus] = useState<Awaited<ReturnType<typeof fetchGbpStatus>> | null>(null)
  const [plans, setPlans] = useState<GbpPlan[]>([])
  const [latest, setLatest] = useState<Record<string, unknown> | null>(null)
  const [suggestions, setSuggestions] = useState<Awaited<ReturnType<typeof fetchGbpSuggestions>> | null>(
    null,
  )
  const [drafts, setDrafts] = useState<GmbDraft[]>([])
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null)
  const [msg, setMsg] = useState('')
  const [liveAction, setLiveAction] = useState<{ draftId: string } | null>(null)
  const [draftForm, setDraftForm] = useState<GmbDraft>({ title: '', body: '', brand: scopeBrand })
  const [editingId, setEditingId] = useState<string | null>(null)
  const [searchTerms, setSearchTerms] = useState<GmbSearchTerms | null>(null)

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const loadPlans = useCallback(() => {
    fetchGbpStatus().then(setStatus).catch(() => setStatus(null))
    fetchGbpPlans(scopeBrand, 30)
      .then((r) => setPlans(r.plans || []))
      .catch(() => setPlans([]))
    fetchGbpLatestPlan(scopeBrand)
      .then(({ status: st, data }) => {
        if (st === 404) setLatest(null)
        else setLatest(data)
      })
      .catch(() => setLatest(null))
  }, [scopeBrand])

  const loadSuggestions = useCallback(() => {
    fetchGbpSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions(null))
  }, [])

  const loadDrafts = useCallback(() => {
    fetchGmbDrafts()
      .then((r) => setDrafts(r.drafts || []))
      .catch(() => setDrafts([]))
  }, [])

  useEffect(() => {
    if (tab !== 'drafts') return
    fetchGmbSearchTerms(scopeBrand).then(setSearchTerms).catch(() => setSearchTerms(null))
  }, [tab, scopeBrand])

  useEffect(() => {
    if (tab === 'plans') loadPlans()
    if (tab === 'suggestions') loadSuggestions()
    if (tab === 'drafts') loadDrafts()
  }, [tab, loadPlans, loadSuggestions, loadDrafts])

  useEffect(() => {
    setDraftForm((f) => ({ ...f, brand: scopeBrand }))
  }, [scopeBrand])

  const brandDrafts = useMemo(
    () => drafts.filter((d) => !d.brand || d.brand === scopeBrand),
    [drafts, scopeBrand],
  )

  async function handlePreview() {
    setMsg('')
    setPreview(null)
    try {
      const data = await previewGbpDailyPlan({ brand_id: scopeBrand, days: 7, posts_per_day: 1 })
      setPreview(data)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Preview failed')
    }
  }

  async function handlePhoto(id: string, file: File) {
    setMsg('')
    try {
      const res = await uploadGmbDraftPhoto(id, file)
      if (!res.ok) {
        setMsg(res.error ?? 'Photo upload failed')
        return
      }
      setMsg('Photo attached. Draft is back in review.')
      loadDrafts()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Photo upload failed')
    }
  }

  async function handleReview(id: string, approve: boolean) {
    setMsg('')
    try {
      if (approve) {
        const res = await approveGmbDraft(id)
        if (!res.ok) {
          setMsg(`Not ready to approve: ${(res.problems?.length ? res.problems : [res.error ?? 'unknown']).join(', ')}`)
          return
        }
        setMsg('Draft approved. It can now go into the daily plan.')
      } else {
        await unapproveGmbDraft(id)
        setMsg('Draft back in review.')
      }
      loadDrafts()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Review failed')
    }
  }

  async function handleScheduleDraft(id: string) {
    setMsg('')
    const { status: st, data } = await scheduleGmbDraft(id)
    if (st === 400) {
      setMsg(String(data.error || data.message || 'no GMB integration under Postiz workspace'))
    } else if (st >= 400) {
      setMsg(String(data.error || `Publish failed (${st})`))
    } else {
      setMsg('Draft published via Postiz.')
      setLiveAction(null)
      loadDrafts()
    }
  }

  async function saveDraft() {
    const body = {
      ...draftForm,
      brand: scopeBrand,
      title: (draftForm.title || '').slice(0, 100),
      body: (draftForm.body || '').slice(0, 1500),
      cta: (draftForm.cta || '').slice(0, 40),
      link: (draftForm.link || '').slice(0, 300),
      imageUrl: (draftForm.imageUrl || '').slice(0, 500),
    }
    try {
      if (editingId) await updateGmbDraft(editingId, body)
      else await createGmbDraft(body)
      setDraftForm({ title: '', body: '', brand: scopeBrand })
      setEditingId(null)
      loadDrafts()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed')
    }
  }

  const classicHref = tab === 'drafts' ? '/?page=gmb' : '/?page=gbp'

  return (
    <div className="space-y-6">
      <PageIntro icon={MapPin} here="/publish/gbp" title="Google Business Profile">
        Daily poster plans and Google drafts for <span className="text-yel">{scopeBrand}</span>. Suggestions cover every brand.
      </PageIntro>

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />
      {msg ? <p className="text-sm text-yel">{msg}</p> : null}

      {tab === 'plans' ? (
        <div className="space-y-4">
          {status ? (
            <p className="flex flex-wrap gap-2 text-sm">
              Credentials{' '}
              <Badge tone={status.credentials_present ? 'green' : 'red'}>
                {status.credentials_present ? 'present ✓' : 'missing ✗'}
              </Badge>
            </p>
          ) : null}
          {latest ? (
            <div className="glass rounded-2xl border border-white/10 p-4 text-sm">
              <p className="font-semibold">Latest plan</p>
              <pre className="mt-2 max-h-40 overflow-auto text-xs text-tx3">
                {JSON.stringify(latest, null, 2)}
              </pre>
            </div>
          ) : (
            <p className="text-sm text-tx3">No plan yet for this brand. That’s normal at the start.</p>
          )}
          <ul className="space-y-2 text-sm">
            {plans.map((plan, i) => (
              <li key={i} className="rounded-xl border border-white/5 px-3 py-2">
                {formatStamp(String(plan.created_at || plan.ts || '')) || 'Plan'} —{' '}
                {String(plan.id || plan.plan_id || i)}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Tip text="Dry-run only — does not push to GBP.">
              <button type="button" className={actionBtn} onClick={handlePreview}>
                Preview plan
              </button>
            </Tip>
          </div>
          {preview ? (
            <div className="glass max-h-96 overflow-auto rounded-2xl border border-white/10 p-4 text-xs">
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'suggestions' ? (
        <div className="space-y-3 text-sm">
          <p className="text-tx3">All brands — suggestions are not brand-scoped.</p>
          {suggestions?.input ? (
            <div className="glass rounded-2xl border border-white/10 p-4">
              <p className="font-semibold">Input</p>
              <pre className="mt-2 max-h-48 overflow-auto text-xs">{JSON.stringify(suggestions.input, null, 2)}</pre>
            </div>
          ) : null}
          {suggestions?.last_post ? (
            <div className="glass rounded-2xl border border-white/10 p-4">
              <p className="font-semibold">Last post</p>
              <pre className="mt-2 max-h-48 overflow-auto text-xs">
                {JSON.stringify(suggestions.last_post, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'drafts' ? (
        <div className="space-y-4">
          <p className="text-sm text-tx3">Drafts filtered to brand {scopeBrand}.</p>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              className={inputCls}
              placeholder="Title (100)"
              maxLength={100}
              value={draftForm.title || ''}
              onChange={(e) => setDraftForm({ ...draftForm, title: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="CTA (40)"
              maxLength={40}
              value={draftForm.cta || ''}
              onChange={(e) => setDraftForm({ ...draftForm, cta: e.target.value })}
            />
            <textarea
              className={`${inputCls} md:col-span-2`}
              placeholder="Body (1500)"
              maxLength={1500}
              rows={4}
              value={draftForm.body || ''}
              onChange={(e) => setDraftForm({ ...draftForm, body: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="Search term this post targets (optional)"
              list="gmb-search-terms"
              maxLength={100}
              value={draftForm.targetQuery || ''}
              onChange={(e) => setDraftForm({ ...draftForm, targetQuery: e.target.value })}
            />
            <datalist id="gmb-search-terms">
              {(searchTerms?.terms ?? []).map((t) => (
                <option key={t.query} value={t.query}>{`${t.impressions} impressions`}</option>
              ))}
            </datalist>
            {searchTerms && !searchTerms.ok ? (
              <p className="text-xs text-tx3">
                No Search Console data for this brand yet ({searchTerms.reason}). Terms will appear here once it is pulled.
              </p>
            ) : null}
            <input
              className={inputCls}
              placeholder="Link (300)"
              maxLength={300}
              value={draftForm.link || ''}
              onChange={(e) => setDraftForm({ ...draftForm, link: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="Image URL (500)"
              maxLength={500}
              value={draftForm.imageUrl || ''}
              onChange={(e) => setDraftForm({ ...draftForm, imageUrl: e.target.value })}
            />
          </div>
          <button type="button" className={actionBtn} onClick={saveDraft}>
            {editingId ? 'Update draft' : 'Create draft'}
          </button>
          <ul className="space-y-2">
            {brandDrafts.map((d) => (
              <li key={d.id} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
                <p className="font-medium">{d.title || '(untitled)'}</p>
                <p className="mt-1 line-clamp-2 text-tx3">{d.body}</p>
                <p className="mt-1 text-xs text-tx3">
                  {d.status === 'approved'
                    ? 'Approved, in the daily plan queue'
                    : d.status === 'published'
                      ? 'Published'
                      : 'Needs review'}
                  {d.imageUrl ? '' : ' · no photo'}
                  {d.link ? '' : ' · no link'}
                </p>
                <label className={`${actionBtn} mt-2 inline-block cursor-pointer`}>
                  {d.imageUrl ? 'Replace photo' : 'Attach photo'}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      e.target.value = ''
                      if (file && d.id) handlePhoto(d.id, file)
                    }}
                  />
                </label>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={actionBtn}
                    onClick={() => {
                      setEditingId(d.id || null)
                      setDraftForm(d)
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className={actionBtn}
                    onClick={async () => {
                      if (!d.id || !window.confirm('Delete this draft?')) return
                      await deleteGmbDraft(d.id)
                      loadDrafts()
                    }}
                  >
                    Delete
                  </button>
                  {d.status === 'approved' ? (
                    <button type="button" className={actionBtn} onClick={() => d.id && handleReview(d.id, false)}>
                      Take back to review
                    </button>
                  ) : (
                    <button type="button" className={primaryBtn} onClick={() => d.id && handleReview(d.id, true)}>
                      Approve
                    </button>
                  )}
                  <Tip text="Only approved drafts can be published.">
                    <button
                      type="button"
                      className={actionBtn}
                      disabled={d.status !== 'approved'}
                      onClick={() => d.id && setLiveAction({ draftId: d.id })}
                    >
                      Publish to GBP via Postiz (live)
                    </button>
                  </Tip>
                </div>
                {liveAction && typeof liveAction === 'object' && liveAction.draftId === d.id ? (
                  <div className="mt-3">
                    <BrandLiveConfirm
                      brandId={scopeBrand}
                      label="Publish this GMB draft via Postiz (live)"
                      onCancel={() => setLiveAction(null)}
                      onConfirm={() => d.id && handleScheduleDraft(d.id)}
                    />
                  </div>
                ) : null}
              </li>
            ))}
            {!brandDrafts.length ? (
              <li className="text-sm text-tx3">No drafts for this brand yet.</li>
            ) : null}
          </ul>
        </div>
      ) : null}

      <ClassicLink href={classicHref} label={tab === 'drafts' ? 'GMB drafts' : 'GBP'} />
    </div>
  )
}
