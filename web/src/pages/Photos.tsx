import { Camera } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useBrandScope } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge } from '../components/ui'

type Status = 'needs-check' | 'approved' | 'rejected'

type PhotoEntry = {
  file: string
  sku: string
  product: string
  view: string
  source: string
  status: Status
  viewable?: boolean
  image_url: string
}

type ReviewPayload = {
  ok: boolean
  counts: Record<string, number>
  entries: PhotoEntry[]
}

type InboxPlan = { kind: string; dest_folder: string; new_name: string; status: 'planned' | 'moved' }

type InboxItem = {
  file: string
  viewable: boolean
  image_url: string
  guess: { kind: string | null; sku: string | null; view: string | null; date: string | null }
  plan: InboxPlan | null
}

type InboxPayload = { ok: boolean; items: InboxItem[]; kinds: string[]; areas: string[] }

type Tab = Status | 'inbox'

const TAB_LABEL: Record<Status, string> = {
  'needs-check': 'Waiting',
  approved: 'Approved',
  rejected: 'Rejected',
}

/** Same as getJson/postJson, but keeps the server's own words when it refuses. */
async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    throw new Error('auth required')
  }
  const data = (await res.json().catch(() => ({}))) as { error?: string }
  if (!res.ok) throw new Error(data.error || `${path} ${res.status}`)
  return data as T
}

const field =
  'w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-tx placeholder:text-tx2'
const pill = 'glass-pill rounded-full border border-white/10 px-4 py-1.5 text-sm font-semibold text-tx hover:border-ac'
const pillOn = 'rounded-full bg-yel px-4 py-1.5 text-sm font-semibold text-bg'

function Missing({ label }: { label: string }) {
  return (
    <div className="flex h-44 items-center justify-center px-3 text-center text-xs text-tx2">{label}</div>
  )
}

function Thumb({ url, viewable, name }: { url: string; viewable?: boolean; name: string }) {
  const [failed, setFailed] = useState(false)
  if (viewable === false) return <Missing label="HEIC or video: cannot preview" />
  if (failed) return <Missing label="Photo not on this server yet" />
  return (
    <img
      src={url}
      alt={name}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-44 w-full bg-white object-contain"
    />
  )
}

function InboxCard({
  item,
  areas,
  brand,
  onChanged,
}: {
  item: InboxItem
  areas: string[]
  brand: string
  onChanged: () => void
}) {
  const g = item.guess
  const [kind, setKind] = useState(item.plan?.kind || g.kind || '')
  const [sku, setSku] = useState(g.sku || '')
  const [area, setArea] = useState(areas[0] || '')
  const [topic, setTopic] = useState('')
  const [date, setDate] = useState(g.date || '')
  const [what, setWhat] = useState(g.view || '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const plan = item.plan

  const save = async () => {
    setBusy(true)
    setErr('')
    try {
      await call('/api/photos/inbox', {
        brand_id: brand,
        file: item.file,
        kind,
        date,
        area: kind === 'facility' ? area : topic,
        what,
        sku: sku.trim(),
      })
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const markMoved = async () => {
    setBusy(true)
    try {
      await call('/api/photos/inbox', { brand_id: brand, file: item.file, status: 'moved' })
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="glass overflow-hidden rounded-2xl border border-white/10">
      <Thumb url={item.image_url} viewable={item.viewable} name={item.file} />
      <div className="space-y-2 p-3 text-sm">
        <div className="break-all text-xs text-tx2">{item.file.replace(/^Inbox\//, '')}</div>
        <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">What is it?</option>
          <option value="product">Product photo</option>
          <option value="facility">Facility</option>
          <option value="service">Service</option>
          <option value="video">Video</option>
        </select>
        {kind === 'product' ? (
          <input className={field} placeholder="SKU" value={sku} onChange={(e) => setSku(e.target.value)} />
        ) : null}
        {kind === 'facility' ? (
          <select className={field} value={area} onChange={(e) => setArea(e.target.value)}>
            {areas.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        ) : null}
        {kind === 'service' || kind === 'video' ? (
          <input
            className={field}
            placeholder={kind === 'service' ? 'Which service (driver fitting)' : 'Topic (new year offer)'}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        ) : null}
        {kind && kind !== 'product' ? (
          <input className={field} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        ) : null}
        <input
          className={field}
          placeholder="What it shows (bay 3 evening)"
          value={what}
          onChange={(e) => setWhat(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={busy || !kind} className={pillOn} onClick={save}>
            Work out the name
          </button>
          {plan && plan.status !== 'moved' ? (
            <button type="button" disabled={busy} className={pill} onClick={markMoved}>
              Mark as moved
            </button>
          ) : null}
        </div>
        {err ? <div className="text-xs text-red">{err}</div> : null}
        {plan ? (
          <div className="break-all rounded-lg bg-white/5 p-2 text-xs">
            {plan.status === 'moved' ? <b>Moved</b> : 'Move'} to <b>{plan.dest_folder}</b>
            <br />
            as <code>{plan.new_name}</code>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function Photos() {
  const { focusBrandId, isAll } = useBrandScope()
  const brand = focusBrandId || ''
  const [tab, setTab] = useState<Tab>('needs-check')
  const [review, setReview] = useState<ReviewPayload | null>(null)
  const [inbox, setInbox] = useState<InboxPayload | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [finding, setFinding] = useState(false)

  const load = useCallback(async () => {
    if (!brand) return
    setError('')
    try {
      const q = `?brand_id=${encodeURIComponent(brand)}`
      setReview(await call<ReviewPayload>(`/api/photos/review${q}`))
      setInbox(await call<InboxPayload>(`/api/photos/inbox${q}`).catch(() => null))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load photos')
    }
  }, [brand])

  useEffect(() => {
    setReview(null)
    setInbox(null)
    setNote('')
    void load()
  }, [load])

  const setStatus = async (file: string, status: Status) => {
    try {
      await call('/api/photos/review', { brand_id: brand, file, status })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    }
  }

  const findNew = async () => {
    setFinding(true)
    setError('')
    try {
      setNote('Getting new files from Drive…')
      await call(`/api/visual-dna/${encodeURIComponent(brand)}/scrape-and-dissect`, {})
      setNote('Matching photos to products…')
      const r = await call<{ added: number; unknown: string[] }>('/api/photos/scan', { brand_id: brand })
      setNote(
        `${r.added} new photo(s) waiting.` + (r.unknown.length ? ` ${r.unknown.length} not matched to a SKU.` : ''),
      )
      await load()
    } catch (e) {
      setNote('')
      setError(e instanceof Error ? e.message : 'Could not finish')
    } finally {
      setFinding(false)
    }
  }

  const waitingInbox = inbox ? inbox.items.filter((i) => i.plan?.status !== 'moved').length : 0
  const list = review ? review.entries.filter((e) => e.status === tab) : []
  list.sort((a, b) => a.product.localeCompare(b.product) || a.file.localeCompare(b.file))

  return (
    <div className="space-y-6">
      <PageIntro icon={Camera} badge="Photos" here="/photos" title="Photos">
        Approve a product photo only if it shows the exact make and model. Approved photos are the only ones the
        planner uses. Files dropped in the Drive Inbox appear here to be sorted.
      </PageIntro>

      {!brand || isAll ? (
        <div className="glass rounded-2xl border border-white/10 p-6 text-tx2">
          Pick one brand at the top first. Photos are kept per brand.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {(Object.keys(TAB_LABEL) as Status[]).map((s) => (
              <button key={s} type="button" className={tab === s ? pillOn : pill} onClick={() => setTab(s)}>
                {TAB_LABEL[s]} ({review?.counts?.[s] ?? 0})
              </button>
            ))}
            <button type="button" className={tab === 'inbox' ? pillOn : pill} onClick={() => setTab('inbox')}>
              Drive Inbox ({waitingInbox})
            </button>
            <div className="flex-1" />
            {note ? <span className="text-xs text-tx2">{note}</span> : null}
            <button type="button" disabled={finding} className={pill} onClick={findNew}>
              Look for new photos
            </button>
          </div>

          {error ? <div className="text-sm text-red">{error}</div> : null}

          {tab === 'inbox' ? (
            !inbox || inbox.items.length === 0 ? (
              <p className="text-tx2">
                The Inbox is empty. Drop files in this brand&apos;s Drive Inbox folder, then press Look for new
                photos.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {inbox.items.map((item) => (
                  <InboxCard
                    key={item.file + (item.plan?.new_name || '')}
                    item={item}
                    areas={inbox.areas}
                    brand={brand}
                    onChanged={load}
                  />
                ))}
              </div>
            )
          ) : list.length === 0 ? (
            <p className="text-tx2">
              {tab === 'needs-check'
                ? 'Nothing is waiting. New photos appear here after you press Look for new photos.'
                : 'None here yet.'}
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {list.map((e) => (
                <div key={e.file} className="glass overflow-hidden rounded-2xl border border-white/10">
                  <Thumb url={e.image_url} viewable={e.viewable} name={e.product} />
                  <div className="space-y-2 p-3 text-sm">
                    <div className="font-semibold">{e.product}</div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-tx2">
                      <Badge>{e.sku}</Badge>
                      <span>
                        {e.view} · {e.source}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {e.status !== 'approved' ? (
                        <button type="button" className={pillOn} onClick={() => setStatus(e.file, 'approved')}>
                          Approve
                        </button>
                      ) : null}
                      {e.status !== 'rejected' ? (
                        <button type="button" className={pill} onClick={() => setStatus(e.file, 'rejected')}>
                          Reject
                        </button>
                      ) : null}
                      {e.status !== 'needs-check' ? (
                        <button type="button" className={pill} onClick={() => setStatus(e.file, 'needs-check')}>
                          Back to waiting
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
