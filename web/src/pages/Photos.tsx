import { Camera } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrandScope } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge } from '../components/ui'
import { FILTER_QUERY, PHOTO_QUERY, photoFilterFromQuery } from '../lib/backNav'
import { actorName } from '../lib/plan'

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

type VideoRow = {
  id: string
  name: string
  url: string
  parsed: {
    date: string | null
    topic: string | null
    what: string | null
    format: string | null
    version: string | null
    follows_rules: boolean
  }
  has_caption_file: boolean
  caption_file_id: string | null
  caption_url: string | null
  caption: string | null
}

type VideoPayload = {
  ok: boolean
  bridge?: boolean
  stages: { stage: string; label: string; videos: VideoRow[] }[]
}

type Tab = Status | 'inbox' | 'video'

const TAB_LABEL: Record<Status, string> = {
  'needs-check': 'Waiting',
  approved: 'Approved',
  rejected: 'Rejected',
}

/** Same as getJson/postJson, but keeps the server's own words when it refuses. */
async function call<T>(path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: body === undefined && !extraHeaders ? undefined : { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders },
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

/** Tomorrow 09:00 in the browser's own time, as a datetime-local value. */
function tomorrowAt9(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(9, 0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const VIDEO_CHANNELS: [string, string][] = [
  ['instagram', 'Instagram'],
  ['facebook', 'Facebook'],
  ['youtube', 'YouTube (private until you publish it there)'],
]

function VideoList({
  data,
  brand,
  onChanged,
}: {
  data: VideoPayload
  brand: string
  onChanged: () => void
}) {
  const bridge = !!data.bridge
  const [copied, setCopied] = useState('')
  const [confirming, setConfirming] = useState('')
  const [sending, setSending] = useState('')
  const [result, setResult] = useState<Record<string, string>>({})
  const [mode, setMode] = useState<'draft' | 'schedule'>('draft')
  const [channel, setChannel] = useState('instagram')
  const [asap, setAsap] = useState(false)
  const [when, setWhen] = useState(tomorrowAt9())
  const [editing, setEditing] = useState('')
  const [editText, setEditText] = useState('')
  const [posting, setPosting] = useState('')
  const [confirmPosted, setConfirmPosted] = useState('')
  const say = (id: string, text: string) => setResult((prev) => ({ ...prev, [id]: text }))
  const channelName = VIDEO_CHANNELS.find(([k]) => k === channel)?.[1].split(' (')[0] || 'Instagram'

  const sendDraft = async (v: VideoRow) => {
    // The calendar books a slot only for a named person; the name is asked once and remembered.
    const name = actorName()
    if (!name) {
      say(v.id, 'Nothing was sent. Type your name when asked, so the calendar can record who booked it.')
      return
    }
    setSending(v.id)
    setConfirming('')
    try {
      const r = await call<{
        channel?: string
        platform?: string
        publish_at_local?: string
        moved_to_minimum?: boolean
        calendar_item?: string | null
      }>('/api/photos/videos/draft', {
        brand_id: brand,
        file_id: v.id,
        mode,
        channel,
        asap: mode === 'schedule' && asap,
        // the browser's own time zone travels with the time, so 9:00 means 9:00 where you are
        publish_at: mode === 'schedule' && !asap ? new Date(when).toISOString() : undefined,
      }, { 'X-Actor-Display-Name': name })
      const where = ` on ${r.platform || channelName}${r.channel ? ` (${r.channel})` : ''}`
      const text =
        mode === 'draft'
          ? `Draft created in Postiz${where}. Nothing is published.`
          : `Scheduled in Postiz${where} for ${r.publish_at_local} (South African time).` +
            (r.moved_to_minimum ? ' That was too soon, so it was moved to 5 minutes from now.' : '')
      say(v.id, text + (r.calendar_item ? ' It is on the calendar.' : ' It could not be added to the calendar.'))
    } catch (e) {
      say(v.id, e instanceof Error ? e.message : 'Could not send')
    } finally {
      setSending('')
    }
  }

  const markPosted = async (v: VideoRow) => {
    const name = actorName()
    if (!name) {
      say(v.id, 'Nothing was moved. Type your name when asked, so the calendar can record who did it.')
      return
    }
    setPosting(v.id)
    setConfirmPosted('')
    try {
      const r = await call<{ moved?: string[]; calendar_error?: string | null }>(
        '/api/photos/videos/posted',
        { brand_id: brand, file_id: v.id },
        { 'X-Actor-Display-Name': name },
      )
      say(v.id, `Moved to Published (${(r.moved || []).length} file${(r.moved || []).length === 1 ? '' : 's'}).` +
        (r.calendar_error ? ' The calendar could not be updated.' : ''))
      onChanged()
    } catch (e) {
      say(v.id, e instanceof Error ? e.message : 'Could not move it')
    } finally {
      setPosting('')
    }
  }

  const saveCaption = async (v: VideoRow) => {
    setSending(v.id)
    try {
      await call('/api/photos/videos/caption', { brand_id: brand, file_id: v.id, caption: editText })
      setEditing('')
      say(v.id, 'Caption saved. Drive can take a few seconds to show it.')
      onChanged()
    } catch (e) {
      say(v.id, e instanceof Error ? e.message : 'Could not save the caption')
    } finally {
      setSending('')
    }
  }

  const copy = async (name: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(name)
      window.setTimeout(() => setCopied(''), 2000)
    } catch {
      /* clipboard blocked: the caption is still on screen to select */
    }
  }

  return (
    <div className="space-y-8">
      {!bridge ? (
        <p className="rounded-xl border border-yel/30 bg-yel/5 px-4 py-3 text-sm text-tx2">
          Mark posted and Edit caption need the Drive bridge, which is not set up yet. Until then, edit the caption
          file in Drive and ask Claude to move posted videos. Setup steps are in <code>docs/drive-bridge/SETUP.md</code>.
        </p>
      ) : null}
      {data.stages.map((stage) => (
        <section key={stage.stage} className="space-y-3">
          <h2 className="font-display text-2xl font-semibold">
            {stage.label} <span className="text-base text-tx2">({stage.videos.length})</span>
          </h2>
          {stage.videos.length === 0 ? (
            <p className="text-sm text-tx2">
              Nothing in <code>Video/{stage.stage}</code> yet.
            </p>
          ) : (
            <div className="space-y-3">
              {stage.videos.map((v) => (
                <div key={v.name} className="glass rounded-2xl border border-white/10 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold break-all">{v.name}</span>
                    {v.parsed.follows_rules ? (
                      <>
                        <Badge>{v.parsed.date}</Badge>
                        <Badge>{v.parsed.topic}</Badge>
                        {v.parsed.format ? <Badge tone="blue">{v.parsed.format}</Badge> : null}
                        {v.parsed.version ? <Badge>{v.parsed.version}</Badge> : null}
                        {v.parsed.what ? <Badge>{v.parsed.what}</Badge> : null}
                      </>
                    ) : (
                      <Badge tone="gold">Name does not follow the rules</Badge>
                    )}
                    <div className="flex-1" />
                    <a className={pill} href={v.url} target="_blank" rel="noreferrer">
                      Open in Drive
                    </a>
                  </div>
                  {stage.stage === '2-ready-to-publish' ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {confirming === v.id ? (
                        <div className="w-full space-y-3 rounded-xl bg-white/5 p-3">
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <span>Where:</span>
                            <select className={field + ' !w-auto'} value={channel} onChange={(e) => setChannel(e.target.value)}>
                              {VIDEO_CHANNELS.map(([k, label]) => (
                                <option key={k} value={k}>
                                  {label}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="flex flex-wrap gap-4 text-sm">
                            <label className="flex items-center gap-2">
                              <input type="radio" checked={mode === 'draft'} onChange={() => setMode('draft')} />
                              Save as a draft in Postiz (nothing is published)
                            </label>
                            <label className="flex items-center gap-2">
                              <input type="radio" checked={mode === 'schedule'} onChange={() => setMode('schedule')} />
                              Schedule it to post by itself
                            </label>
                          </div>
                          {mode === 'schedule' ? (
                            <div className="flex flex-wrap items-center gap-3 text-sm">
                              <input
                                type="datetime-local"
                                className={field + ' !w-auto'}
                                value={when}
                                disabled={asap}
                                onChange={(e) => setWhen(e.target.value)}
                              />
                              <label className="flex items-center gap-2">
                                <input type="checkbox" checked={asap} onChange={(e) => setAsap(e.target.checked)} />
                                As soon as possible (5 minutes from now)
                              </label>
                              <span className="text-xs text-tx2">
                                Never sooner than 5 minutes ahead, so Postiz has time to load the video.
                              </span>
                            </div>
                          ) : null}
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm">
                              {mode === 'draft'
                                ? `Create a draft on ${channelName}?`
                                : `This will post to ${channelName} by itself at that time. Schedule it?`}
                            </span>
                            <button
                              type="button"
                              className={pillOn}
                              disabled={mode === 'schedule' && !asap && !when}
                              onClick={() => void sendDraft(v)}
                            >
                              {mode === 'draft' ? 'Yes, create the draft' : 'Yes, schedule it'}
                            </button>
                            <button type="button" className={pill} onClick={() => setConfirming('')}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : confirmPosted === v.id ? (
                        <>
                          <span className="text-sm">Move this video and its caption to Published?</span>
                          <button type="button" className={pillOn} onClick={() => void markPosted(v)}>
                            Yes, it has been posted
                          </button>
                          <button type="button" className={pill} onClick={() => setConfirmPosted('')}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            disabled={sending === v.id || !v.caption}
                            className={pill}
                            onClick={() => setConfirming(v.id)}
                          >
                            {sending === v.id ? 'Sending to Postiz…' : 'Send to Postiz'}
                          </button>
                          <button
                            type="button"
                            disabled={!bridge || posting === v.id}
                            className={pill}
                            title={bridge ? '' : 'Needs the Drive bridge'}
                            onClick={() => setConfirmPosted(v.id)}
                          >
                            {posting === v.id ? 'Moving…' : 'Mark posted'}
                          </button>
                        </>
                      )}
                    </div>
                  ) : null}
                  {result[v.id] ? <p className="mt-2 text-sm text-tx2">{result[v.id]}</p> : null}
                  {stage.stage !== '1-raw' ? (
                    editing === v.id ? (
                      <div className="mt-3 space-y-2">
                        <textarea
                          className={field + ' min-h-32'}
                          value={editText}
                          maxLength={2200}
                          onChange={(e) => setEditText(e.target.value)}
                        />
                        <div className="flex flex-wrap items-center gap-2">
                          <button type="button" disabled={sending === v.id || !editText.trim()} className={pillOn} onClick={() => void saveCaption(v)}>
                            {sending === v.id ? 'Saving…' : 'Save caption'}
                          </button>
                          <button type="button" className={pill} onClick={() => setEditing('')}>
                            Cancel
                          </button>
                          <span className="text-xs text-tx2">{editText.length} / 2,200</span>
                        </div>
                      </div>
                    ) : v.caption ? (
                      <div className="mt-3 space-y-2">
                        <div className="rounded-lg bg-white/5 p-3 text-sm whitespace-pre-wrap">{v.caption}</div>
                        <div className="flex flex-wrap gap-2">
                          <button type="button" className={pill} onClick={() => copy(v.name, v.caption || '')}>
                            {copied === v.name ? 'Copied' : 'Copy caption'}
                          </button>
                          {bridge ? (
                            <button
                              type="button"
                              className={pill}
                              onClick={() => {
                                setEditing(v.id)
                                setEditText(v.caption || '')
                              }}
                            >
                              Edit caption
                            </button>
                          ) : v.caption_url ? (
                            <a className={pill} href={v.caption_url} target="_blank" rel="noreferrer">
                              Open caption in Drive
                            </a>
                          ) : null}
                        </div>
                      </div>
                    ) : (
                      <div className="mt-3 space-y-2">
                        <p className="text-sm text-tx2">
                          {v.has_caption_file
                            ? 'The caption file is empty.'
                            : 'No caption file. Add a .txt with the same name next to the video.'}
                        </p>
                        {bridge ? (
                          <button
                            type="button"
                            className={pill}
                            onClick={() => {
                              setEditing(v.id)
                              setEditText('')
                            }}
                          >
                            Write the caption
                          </button>
                        ) : null}
                      </div>
                    )
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
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
  const [params, setParams] = useSearchParams()
  const { focusBrandId, isAll } = useBrandScope()
  const brand = focusBrandId || ''
  const [tab, setTab] = useState<Tab>(() => photoFilterFromQuery(params.get(FILTER_QUERY)))
  const [review, setReview] = useState<ReviewPayload | null>(null)
  const [inbox, setInbox] = useState<InboxPayload | null>(null)
  const [video, setVideo] = useState<VideoPayload | null>(null)
  const [videoBusy, setVideoBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [finding, setFinding] = useState(false)

  useEffect(() => {
    setTab(photoFilterFromQuery(params.get(FILTER_QUERY)))
  }, [params])

  const openFile = params.get(PHOTO_QUERY) || ''

  const setTabWithQuery = useCallback(
    (next: Tab) => {
      setTab(next)
      const p = new URLSearchParams(params)
      if (next === 'needs-check') p.delete(FILTER_QUERY)
      else p.set(FILTER_QUERY, next)
      p.delete(PHOTO_QUERY)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  function openPhoto(file: string) {
    setParams((prev) => {
      const p = new URLSearchParams(prev)
      p.set(PHOTO_QUERY, file)
      return p
    })
  }

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
    setVideo(null)
    setNote('')
    void load()
  }, [load])

  // Videos come from a live look at Drive, so they load when the tab is opened.
  const loadVideo = useCallback(async (fresh = false) => {
    if (!brand) return
    setVideoBusy(true)
    setError('')
    try {
      setVideo(await call<VideoPayload>(`/api/photos/videos?brand_id=${encodeURIComponent(brand)}${fresh ? '&refresh=1' : ''}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read the videos')
    } finally {
      setVideoBusy(false)
    }
  }, [brand])

  useEffect(() => {
    if (tab === 'video' && !video) void loadVideo()
  }, [tab, video, loadVideo])

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
              <button key={s} type="button" className={tab === s ? pillOn : pill} onClick={() => setTabWithQuery(s)}>
                {TAB_LABEL[s]} ({review?.counts?.[s] ?? 0})
              </button>
            ))}
            <button type="button" className={tab === 'inbox' ? pillOn : pill} onClick={() => setTabWithQuery('inbox')}>
              Drive Inbox ({waitingInbox})
            </button>
            <button type="button" className={tab === 'video' ? pillOn : pill} onClick={() => setTabWithQuery('video')}>
              Video
            </button>
            <div className="flex-1" />
            {note ? <span className="text-xs text-tx2">{note}</span> : null}
            <button type="button" disabled={finding} className={pill} onClick={findNew}>
              Look for new photos
            </button>
          </div>

          {error ? <div className="text-sm text-red">{error}</div> : null}

          {tab === 'video' ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <p className="text-sm text-tx2">
                  Videos in this brand&apos;s Drive <code>Video</code> folder, by stage. The folder is the status.
                  Posting is still done by hand.
                </p>
                <div className="flex-1" />
                <button type="button" disabled={videoBusy} className={pill} onClick={() => void loadVideo(true)}>
                  {videoBusy ? 'Reading Drive…' : 'Refresh'}
                </button>
              </div>
              {video ? <VideoList data={video} brand={brand} onChanged={() => void loadVideo(true)} /> : videoBusy ? <p className="text-tx2">Reading Drive…</p> : null}
            </div>
          ) : tab === 'inbox' ? (
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
                <div
                  key={e.file}
                  className={`glass overflow-hidden rounded-2xl border border-white/10 ${
                    openFile === e.file ? 'ring-2 ring-yel' : ''
                  }`}
                >
                  <button type="button" className="block w-full" onClick={() => openPhoto(e.file)} aria-label={`Open ${e.product}`}>
                    <Thumb url={e.image_url} viewable={e.viewable} name={e.product} />
                  </button>
                  <div className="space-y-2 p-3 text-sm">
                    <button type="button" className="font-semibold" onClick={() => openPhoto(e.file)}>
                      {e.product}
                    </button>
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
