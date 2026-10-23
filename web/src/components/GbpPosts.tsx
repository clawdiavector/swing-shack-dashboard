import { useState } from 'react'
import type { GmbDraft } from '../lib/api'

export type GbpStage = 'check' | 'ready' | 'sent'

const btn = 'rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50'
const primary = 'rounded-full bg-yel px-5 py-2.5 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-50'
const field =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

/** Which of the three steps a draft is in. */
export function postStage(d: GmbDraft): GbpStage {
  if (d.status === 'approved') return 'ready'
  if (d.status === 'published' || d.status === 'scheduled') return 'sent'
  return 'check'
}

export const PROBLEM_WORDS: Record<string, string> = {
  photo_missing: 'needs a photo',
  link_missing: 'needs a link',
  link_not_brand_domain: 'the link must go to this brand’s own website',
  body_empty: 'needs some text',
  target_query_not_in_body: 'the search phrase is not in the text',
  photo_match_not_confirmed: 'tick the box to say the photo matches the text',
  em_dash_or_en_dash_present: 'has a long dash in it, use a comma or full stop instead',
  unknown_brand: 'this post has no brand',
}

export function problemWords(codes: string[]): string[] {
  return codes.map((c) => PROBLEM_WORDS[c] ?? (c.startsWith('stick_location') || c.startsWith('ss_location') ? 'names a place this brand is not in' : c.replace(/_/g, ' ')))
}

/** What the person should do next, in one plain sentence. */
export function nextStep(counts: Record<GbpStage, number>): string {
  if (counts.ready > 0)
    return `${counts.ready} post${counts.ready === 1 ? ' is' : 's are'} approved and waiting. Open “Ready to send” and press Publish when you want one to go out.`
  if (counts.check > 0)
    return `${counts.check} post${counts.check === 1 ? ' needs' : 's need'} your check. Open “To check”, look at the photo, tick the box and press Approve.`
  if (counts.sent > 0) return 'Everything has been sent. Press “New post” to write another one.'
  return 'No posts yet. Press “New post” to write the first one.'
}

export function StepBar({
  tab,
  counts,
  onChange,
}: {
  tab: string
  counts: Record<GbpStage, number>
  onChange: (id: string) => void
}) {
  const steps: { id: GbpStage; n: number; label: string; hint: string }[] = [
    { id: 'check', n: 1, label: 'To check', hint: 'Look at the photo and text' },
    { id: 'ready', n: 2, label: 'Ready to send', hint: 'Approved, press Publish' },
    { id: 'sent', n: 3, label: 'Sent', hint: 'Already on Google' },
  ]
  return (
    <div className="grid gap-2 sm:grid-cols-3" role="tablist" aria-label="Steps">
      {steps.map((s) => (
        <button
          key={s.id}
          type="button"
          role="tab"
          aria-selected={tab === s.id}
          onClick={() => onChange(s.id)}
          className={`rounded-2xl border px-4 py-3 text-left ${
            tab === s.id ? 'border-yel bg-yel/10' : 'border-white/10 hover:border-ac'
          }`}
        >
          <span className="block text-xs text-tx3">Step {s.n}</span>
          <span className="block text-base font-semibold">
            {s.label} <span className="text-yel">({counts[s.id]})</span>
          </span>
          <span className="block text-xs text-tx3">{s.hint}</span>
        </button>
      ))}
    </div>
  )
}

export type PostHandlers = {
  onApprove: (id: string) => void
  onUnapprove: (id: string) => void
  onPublish: (id: string) => void
  onDelete: (id: string) => void
  onPhoto: (id: string, file: File) => void
  onSave: (id: string, patch: GmbDraft) => Promise<boolean>
}

export function PostForm({
  value,
  onChange,
  terms,
}: {
  value: GmbDraft
  onChange: (v: GmbDraft) => void
  terms: string[]
}) {
  const label = 'block text-xs font-semibold text-tx2'
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <label className={label}>
        Heading
        <input className={`${field} mt-1`} maxLength={100} value={value.title || ''} onChange={(e) => onChange({ ...value, title: e.target.value })} />
      </label>
      <label className={label}>
        Words on the button (for example “Book a fitting”)
        <input className={`${field} mt-1`} maxLength={40} value={value.cta || ''} onChange={(e) => onChange({ ...value, cta: e.target.value })} />
      </label>
      <label className={`${label} md:col-span-2`}>
        The post text
        <textarea className={`${field} mt-1`} rows={5} maxLength={1500} value={value.body || ''} onChange={(e) => onChange({ ...value, body: e.target.value })} />
      </label>
      <label className={label}>
        Where the button goes (the brand’s website page)
        <input className={`${field} mt-1`} maxLength={300} value={value.link || ''} onChange={(e) => onChange({ ...value, link: e.target.value })} />
      </label>
      <label className={label}>
        Search phrase this post is about (optional, must appear in the text)
        <input
          className={`${field} mt-1`}
          list="gbp-terms"
          maxLength={100}
          value={value.targetQuery || ''}
          onChange={(e) => onChange({ ...value, targetQuery: e.target.value })}
        />
        <datalist id="gbp-terms">
          {terms.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>
    </div>
  )
}

const STAGE_BADGE: Record<GbpStage, { text: string; cls: string }> = {
  check: { text: 'Needs your check', cls: 'bg-yel/15 text-yel' },
  ready: { text: 'Approved, ready to send', cls: 'bg-ac/15 text-ac' },
  sent: { text: 'Sent to Google', cls: 'glass-pill text-tx2' },
}

export function PostCard({
  d,
  busy,
  terms,
  handlers,
  brandName,
  suggestedWhy,
}: {
  d: GmbDraft
  busy: boolean
  terms: string[]
  handlers: PostHandlers
  brandName?: string
  suggestedWhy?: string
}) {
  const stage = postStage(d)
  const id = d.id ?? ''
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<GmbDraft>(d)
  const [photoOk, setPhotoOk] = useState(false)
  const missing: string[] = []
  if (!d.imageUrl) missing.push('needs a photo')
  if (!d.link) missing.push('needs a link')
  if (!(d.body || '').trim()) missing.push('needs some text')
  const photo = d.imageUrl && id ? `/api/intel/gmb/draft/${encodeURIComponent(id)}/photo-file?v=${encodeURIComponent(d.updatedAt ?? '')}` : null
  const badge = STAGE_BADGE[stage]

  return (
    <li className={`glass rounded-2xl border p-4 ${suggestedWhy ? 'border-yel' : 'border-white/10'}`}>
      {suggestedWhy ? (
        <p className="mb-3 rounded-xl bg-yel/10 px-3 py-2 text-sm">
          <span className="font-semibold text-yel">Suggested to go out next.</span> {suggestedWhy}
        </p>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="sm:w-56 sm:shrink-0">
          {photo ? (
            <a href={photo} target="_blank" rel="noreferrer" title="Open the photo full size">
              <img src={photo} alt="Photo for this post" loading="lazy" className="max-h-64 w-full rounded-xl border border-white/10 object-cover" />
            </a>
          ) : (
            <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-white/20 text-sm text-tx3">
              No photo yet
            </div>
          )}
          {stage !== 'sent' ? (
            <label className={`${btn} mt-2 block cursor-pointer text-center`}>
              {d.imageUrl ? 'Change photo' : 'Add a photo'}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  e.target.value = ''
                  if (file && id) handlers.onPhoto(id, file)
                }}
              />
            </label>
          ) : null}
        </div>
        <div className="min-w-0 flex-1">
          <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${badge.cls}`}>{badge.text}</span>
          {brandName ? <span className="ml-2 inline-block rounded-full glass-pill px-2.5 py-1 text-xs font-semibold text-tx2">{brandName}</span> : null}
          <h3 className="mt-2 text-base font-semibold">{d.title || '(no heading)'}</h3>
          <p className="mt-1 whitespace-pre-line text-sm">{d.body}</p>
          <p className="mt-2 text-xs text-tx3">
            Button: <span className="text-tx2">{d.cta || 'none'}</span> · Goes to: <span className="text-tx2">{d.link || 'no link yet'}</span>
            {d.targetQuery ? (
              <>
                {' '}
                · Search phrase: <span className="text-tx2">{d.targetQuery}</span>
              </>
            ) : null}
          </p>
          {stage !== 'sent' && missing.length ? <p className="mt-2 text-sm text-red-300">Before it can go out: {missing.join(', ')}.</p> : null}

          {stage === 'check' ? (
            <div className="mt-3 space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={photoOk} onChange={(e) => setPhotoOk(e.target.checked)} />
                The photo shows what the text says
              </label>
              <div className="flex flex-wrap gap-2">
                <button type="button" className={primary} disabled={busy || !photoOk || missing.length > 0} onClick={() => handlers.onApprove(id)}>
                  Approve
                </button>
                <button type="button" className={btn} onClick={() => setEditing((v) => !v)}>
                  {editing ? 'Close editor' : 'Edit the words'}
                </button>
                <button type="button" className={btn} disabled={busy} onClick={() => handlers.onDelete(id)}>
                  Delete
                </button>
              </div>
              {!photoOk ? <p className="text-xs text-tx3">Tick the box above to unlock Approve.</p> : null}
            </div>
          ) : null}

          {stage === 'ready' ? (
            <div className="mt-3 space-y-2">
              <div className="flex flex-wrap gap-2">
                <button type="button" className={primary} disabled={busy} onClick={() => handlers.onPublish(id)}>
                  Publish to Google
                </button>
                <button type="button" className={btn} onClick={() => setEditing((v) => !v)}>
                  {editing ? 'Close editor' : 'Edit the words'}
                </button>
                <button type="button" className={btn} disabled={busy} onClick={() => handlers.onUnapprove(id)}>
                  Move back to “To check”
                </button>
              </div>
              <p className="text-xs text-tx3">Publish sends it to the Google listing. You will be asked to confirm first.</p>
            </div>
          ) : null}

          {stage === 'sent' ? <p className="mt-3 text-sm text-tx3">This post has been sent. Nothing more to do.</p> : null}

          {editing ? (
            <div className="mt-4 space-y-3 rounded-xl border border-white/10 p-3">
              <PostForm value={form} onChange={setForm} terms={terms} />
              <p className="text-xs text-tx3">Saving a change moves an approved post back to “To check”.</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={primary}
                  disabled={busy}
                  onClick={async () => {
                    if (await handlers.onSave(id, form)) setEditing(false)
                  }}
                >
                  Save changes
                </button>
                <button
                  type="button"
                  className={btn}
                  onClick={() => {
                    setForm(d)
                    setEditing(false)
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </li>
  )
}
