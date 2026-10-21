import { MapPin } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand, useBrandScope } from '../../components/BrandSwitch'
import { PageIntro } from '../../components/chrome'
import {
  nextStep,
  postStage,
  problemWords,
  PostCard,
  PostForm,
  StepBar,
  type GbpStage,
  type PostHandlers,
} from '../../components/GbpPosts'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import {
  approveGmbDraft,
  createGmbDraft,
  deleteGmbDraft,
  fetchGbpLatestPlan,
  fetchGbpPlans,
  fetchGbpStatus,
  fetchGbpSuggestions,
  fetchGmbDrafts,
  fetchGmbSearchTerms,
  previewGbpDailyPlan,
  scheduleGmbDraft,
  unapproveGmbDraft,
  updateGmbDraft,
  uploadGmbDraftPhoto,
  type GbpPlan,
  type GmbDraft,
  type GmbSearchTerms,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'

const actionBtn =
  'rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50'
const primaryBtn = 'rounded-full bg-yel px-5 py-2.5 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-50'

type GbpTab = GbpStage | 'new' | 'more'

const BRAND_NAMES: Record<string, string> = { 'swing-shack': 'Swing Shack', stick: 'Stick', 'bag-drop': 'Bag Drop' }

function resolveTab(raw: string | null): GbpTab {
  if (raw === 'check' || raw === 'ready' || raw === 'sent' || raw === 'new' || raw === 'more') return raw
  if (raw === 'plans' || raw === 'suggestions') return 'more'
  return 'check'
}

export function Gbp() {
  const { brandId } = useBrand()
  const { isAll, scope } = useBrandScope()
  const allBrands = isAll
  const scopeBrand = isAll ? (brandId ?? 'swing-shack') : String(scope)
  const nameOf = (id?: string) => BRAND_NAMES[id ?? ''] ?? id ?? ''
  const brandName = allBrands ? 'every brand' : nameOf(scopeBrand)
  const [params, setParams] = useSearchParams()
  const tab = resolveTab(params.get('tab'))
  const [status, setStatus] = useState<Awaited<ReturnType<typeof fetchGbpStatus>> | null>(null)
  const [plans, setPlans] = useState<GbpPlan[]>([])
  const [latest, setLatest] = useState<Record<string, unknown> | null>(null)
  const [suggestions, setSuggestions] = useState<Awaited<ReturnType<typeof fetchGbpSuggestions>> | null>(null)
  const [drafts, setDrafts] = useState<GmbDraft[]>([])
  const [loaded, setLoaded] = useState(false)
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [newPost, setNewPost] = useState<GmbDraft>({ title: '', body: '', brand: scopeBrand })
  const [newBrand, setNewBrand] = useState(scopeBrand)
  const [searchTerms, setSearchTerms] = useState<GmbSearchTerms | null>(null)

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const loadDrafts = useCallback(() => {
    fetchGmbDrafts()
      .then((r) => setDrafts(r.drafts || []))
      .catch(() => setDrafts([]))
      .finally(() => setLoaded(true))
  }, [])

  useEffect(() => {
    loadDrafts()
  }, [loadDrafts])

  useEffect(() => {
    fetchGmbSearchTerms(scopeBrand).then(setSearchTerms).catch(() => setSearchTerms(null))
  }, [scopeBrand])

  useEffect(() => {
    if (tab !== 'more') return
    fetchGbpStatus().then(setStatus).catch(() => setStatus(null))
    fetchGbpPlans(scopeBrand, 30)
      .then((r) => setPlans(r.plans || []))
      .catch(() => setPlans([]))
    fetchGbpLatestPlan(scopeBrand)
      .then(({ status: st, data }) => setLatest(st === 404 ? null : data))
      .catch(() => setLatest(null))
    fetchGbpSuggestions()
      .then(setSuggestions)
      .catch(() => setSuggestions(null))
  }, [tab, scopeBrand])

  useEffect(() => {
    setNewPost((f) => ({ ...f, brand: scopeBrand }))
    setNewBrand(scopeBrand)
  }, [scopeBrand])

  const brandDrafts = useMemo(
    () => (allBrands ? drafts : drafts.filter((d) => !d.brand || d.brand === scopeBrand)),
    [drafts, scopeBrand, allBrands],
  )
  const counts = useMemo(() => {
    const c: Record<GbpStage, number> = { check: 0, ready: 0, sent: 0 }
    for (const d of brandDrafts) c[postStage(d)] += 1
    return c
  }, [brandDrafts])
  const shown = useMemo(
    () =>
      brandDrafts
        .filter((d) => tab === postStage(d))
        .sort((a, b) => String(a.approvedAt || a.updatedAt || '').localeCompare(String(b.approvedAt || b.updatedAt || ''))),
    [brandDrafts, tab],
  )
  const terms = useMemo(() => (searchTerms?.terms ?? []).map((t) => t.query), [searchTerms])

  async function run(fn: () => Promise<void>) {
    setBusy(true)
    setMsg('')
    try {
      await fn()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const handlers: PostHandlers = {
    onApprove: (id) =>
      run(async () => {
        const res = await approveGmbDraft(id, true)
        if (!res.ok) {
          const codes = res.problems?.length ? res.problems : [res.error ?? 'unknown']
          setMsg(`Not approved yet: ${problemWords(codes).join('; ')}.`)
          return
        }
        setMsg('Approved. It is now in “Ready to send”.')
        loadDrafts()
        setTab('ready')
      }),
    onUnapprove: (id) =>
      run(async () => {
        await unapproveGmbDraft(id)
        setMsg('Moved back to “To check”.')
        loadDrafts()
        setTab('check')
      }),
    onPublish: (id) =>
      run(async () => {
        const d = drafts.find((x) => x.id === id)
        const who = nameOf(d?.brand ?? scopeBrand)
        if (!window.confirm(`Publish “${d?.title ?? 'this post'}” to the ${who} Google listing? It goes live.`)) return
        const { status: st, data } = await scheduleGmbDraft(id)
        if (st >= 400) {
          const err = String(data.error || data.message || `Publish failed (${st})`)
          setMsg(
            err.includes('no GMB integration')
              ? `Not sent: the ${nameOf(d?.brand ?? scopeBrand)} Google listing is not connected in Postiz yet. Ask Kyle to connect it, then press Publish again.`
              : `Not sent: ${err}`,
          )
          return
        }
        setMsg('Sent to Google. It is now in “Sent”. Google can take a few minutes to show it.')
        loadDrafts()
        setTab('sent')
      }),
    onDelete: (id) =>
      run(async () => {
        if (!window.confirm('Delete this post for good?')) return
        await deleteGmbDraft(id)
        setMsg('Deleted.')
        loadDrafts()
      }),
    onPhoto: (id, file) =>
      run(async () => {
        const res = await uploadGmbDraftPhoto(id, file)
        if (!res.ok) {
          setMsg(res.error ?? 'The photo did not upload.')
          return
        }
        setMsg('Photo changed. The post is back in “To check”, so look at it again.')
        loadDrafts()
        setTab('check')
      }),
    onSave: async (id, patch) => {
      setBusy(true)
      setMsg('')
      try {
        await updateGmbDraft(id, {
          title: (patch.title || '').slice(0, 100),
          body: (patch.body || '').slice(0, 1500),
          cta: (patch.cta || '').slice(0, 40),
          link: (patch.link || '').slice(0, 300),
          targetQuery: (patch.targetQuery || '').slice(0, 100),
        })
        setMsg('Saved. The post is in “To check”.')
        loadDrafts()
        setTab('check')
        return true
      } catch (e) {
        setMsg(e instanceof Error ? e.message : 'Save failed')
        return false
      } finally {
        setBusy(false)
      }
    },
  }

  async function createPost() {
    await run(async () => {
      await createGmbDraft({
        ...newPost,
        brand: newBrand,
        title: (newPost.title || '').slice(0, 100),
        body: (newPost.body || '').slice(0, 1500),
        cta: (newPost.cta || '').slice(0, 40),
        link: (newPost.link || '').slice(0, 300),
      })
      setNewPost({ title: '', body: '', brand: newBrand })
      setMsg('Post created. Add a photo to it below, then check and approve it.')
      loadDrafts()
      setTab('check')
    })
  }

  async function handlePreview() {
    setMsg('')
    setPreview(null)
    try {
      setPreview(await previewGbpDailyPlan({ brand_id: scopeBrand, days: 7, posts_per_day: 1 }))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Preview failed')
    }
  }

  const emptyText: Record<GbpStage, string> = {
    check: `Nothing to check${allBrands ? '' : ` for ${brandName}`}. Press “+ New post” to write one.`,
    ready: 'Nothing approved yet. Approve a post in “To check” and it will appear here.',
    sent: 'Nothing sent yet.',
  }

  return (
    <div className="space-y-6">
      <PageIntro icon={MapPin} here="/publish/gbp" title="Google Business Profile">
        {allBrands ? (
          <>Posts for every brand’s Google listing, each marked with its brand.</>
        ) : (
          <>
            Posts for the <span className="text-yel">{brandName}</span> Google listing.
          </>
        )}{' '}
        Every post goes through three steps: check it, approve it, publish it.
      </PageIntro>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm">{loaded ? nextStep(counts) : 'Loading your posts...'}</p>
        <button type="button" className={primaryBtn} onClick={() => setTab('new')}>
          + New post
        </button>
      </div>

      <StepBar tab={tab} counts={counts} onChange={setTab} />
      {msg ? <p className="rounded-xl border border-yel/30 bg-yel/10 px-4 py-3 text-sm text-yel">{msg}</p> : null}

      {tab === 'check' || tab === 'ready' || tab === 'sent' ? (
        <ul className="space-y-4">
          {shown.map((d) => (
            <PostCard key={`${d.id}-${d.updatedAt}`} d={d} busy={busy} terms={terms} handlers={handlers} brandName={nameOf(d.brand)} />
          ))}
          {loaded && !shown.length ? <li className="text-sm text-tx3">{emptyText[tab]}</li> : null}
        </ul>
      ) : null}

      {tab === 'new' ? (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">New post{allBrands ? '' : ` for ${brandName}`}</h2>
          {allBrands ? (
            <label className="block text-xs font-semibold text-tx2">
              Which brand is this post for?
              <select
                className="mt-1 w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx md:w-64"
                value={newBrand}
                onChange={(e) => setNewBrand(e.target.value)}
              >
                {Object.entries(BRAND_NAMES).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <PostForm value={newPost} onChange={setNewPost} terms={terms} />
          {searchTerms && !searchTerms.ok ? (
            <p className="text-xs text-tx3">No Google search data for this brand yet, so there are no search phrases to pick from.</p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={primaryBtn} disabled={busy || !(newPost.body || '').trim()} onClick={createPost}>
              Create post
            </button>
            <button type="button" className={actionBtn} onClick={() => setTab('check')}>
              Cancel
            </button>
          </div>
          <p className="text-xs text-tx3">After you create it, add a photo on its card in “To check”.</p>
        </div>
      ) : null}

      {tab === 'more' ? (
        <div className="space-y-4 text-sm">
          <h2 className="text-lg font-semibold">Behind the scenes</h2>
          <p className="text-tx3">Technical details for Kyle. You do not need anything on this tab to post.</p>
          {status ? (
            <p className="flex flex-wrap gap-2">
              Google login{' '}
              <Badge tone={status.credentials_present ? 'green' : 'red'}>{status.credentials_present ? 'connected' : 'not connected'}</Badge>
            </p>
          ) : null}
          {latest ? (
            <div className="glass rounded-2xl border border-white/10 p-4">
              <p className="font-semibold">Latest daily plan</p>
              <pre className="mt-2 max-h-40 overflow-auto text-xs text-tx3">{JSON.stringify(latest, null, 2)}</pre>
            </div>
          ) : (
            <p className="text-tx3">No daily plan yet for this brand.</p>
          )}
          <ul className="space-y-2">
            {plans.map((plan, i) => (
              <li key={i} className="rounded-xl border border-white/5 px-3 py-2">
                {formatStamp(String(plan.created_at || plan.ts || '')) || 'Plan'} · {String(plan.id || plan.plan_id || i)}
              </li>
            ))}
          </ul>
          <Tip text="Dry run only. Nothing is sent to Google.">
            <button type="button" className={actionBtn} onClick={handlePreview}>
              Preview a week of posts
            </button>
          </Tip>
          {preview ? (
            <div className="glass max-h-96 overflow-auto rounded-2xl border border-white/10 p-4 text-xs">
              <pre>{JSON.stringify(preview, null, 2)}</pre>
            </div>
          ) : null}
          {suggestions?.input ? (
            <div className="glass rounded-2xl border border-white/10 p-4">
              <p className="font-semibold">What the AI suggestion looked at (all brands)</p>
              <pre className="mt-2 max-h-48 overflow-auto text-xs">{JSON.stringify(suggestions.input, null, 2)}</pre>
            </div>
          ) : null}
          {suggestions?.last_post ? (
            <div className="glass rounded-2xl border border-white/10 p-4">
              <p className="font-semibold">Last AI suggestion (all brands)</p>
              <pre className="mt-2 max-h-48 overflow-auto text-xs">{JSON.stringify(suggestions.last_post, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab !== 'more' ? (
        <button type="button" className="text-xs text-tx3 underline" onClick={() => setTab('more')}>
          Behind the scenes (technical, you can ignore this)
        </button>
      ) : (
        <button type="button" className="text-xs text-tx3 underline" onClick={() => setTab('check')}>
          Back to my posts
        </button>
      )}
      <ClassicLink href="/?page=gmb" label="GMB drafts" />
    </div>
  )
}
