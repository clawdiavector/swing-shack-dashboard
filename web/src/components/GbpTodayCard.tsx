import { useCallback, useEffect, useState } from 'react'
import {
  approveGmbDraft,
  fetchGbpPending,
  publishGbpPending,
  skipGbpPending,
  type GbpActionResult,
  type GbpPending,
} from '../lib/api'

const ghost = 'rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50'
const primary = 'rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-50'

const REASON: Record<string, string> = {
  no_plan: 'No plan yet. Approve a draft on the Google Business Profile page to queue a post.',
  all_actioned: 'Nothing waiting. Approve the next draft on the Google Business Profile page.',
  no_postiz_integration: 'This brand has no Google channel set up, so posts cannot go out.',
  integration_not_found_on_postiz_key: 'The Google channel is not connected in Postiz, so posts cannot go out yet.',
}

function describe(res: GbpActionResult) {
  const extra = res.integrity_violations?.length ? ` (${res.integrity_violations.join(', ')})` : ''
  return res.reason ?? res.error ?? `${res.post_status ?? 'not sent'}${extra}`
}

/** Today's Google Business post for one brand: photo, text, link, and send or skip. */
export function GbpTodayCard({ brandId }: { brandId: string }) {
  const [data, setData] = useState<GbpPending | null>(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [photoOk, setPhotoOk] = useState(false)

  const load = useCallback(() => {
    fetchGbpPending(brandId)
      .then(setData)
      .catch((e: Error) => {
        setData(null)
        setMsg(e.message)
      })
  }, [brandId])

  useEffect(() => {
    load()
  }, [load])

  const post = data?.post ?? null
  const suggestion = !post ? (data?.suggestion?.post ?? null) : null
  const name = data?.display_name ?? brandId

  async function publish() {
    if (!post?.draft_id) return
    if (!window.confirm(`Publish this post to Google Business Profile for ${name}? It goes out live.`)) return
    setBusy(true)
    setMsg('')
    try {
      const res = await publishGbpPending(brandId, post.draft_id)
      setMsg(res.ok ? 'Sent to Google Business Profile.' : `Not sent: ${describe(res)}`)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Send failed')
    } finally {
      setBusy(false)
      load()
    }
  }

  async function approveAndPublish() {
    if (!suggestion?.draft_id) return
    if (!window.confirm(`Approve this draft and publish it to Google Business Profile for ${name}? It goes out live.`)) return
    setBusy(true)
    setMsg('')
    try {
      const ok = await approveGmbDraft(suggestion.draft_id, true)
      if (!ok.ok) {
        setMsg(`Not approved: ${ok.problems?.join(', ') ?? ok.error ?? 'check the draft on the Google Business Profile page'}`)
        return
      }
      const res = await publishGbpPending(brandId, suggestion.draft_id)
      setMsg(res.ok ? 'Sent to Google Business Profile.' : `Approved but not sent: ${describe(res)}`)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Send failed')
    } finally {
      setBusy(false)
      setPhotoOk(false)
      load()
    }
  }

  async function skip() {
    if (!window.confirm(`Skip today's post for ${name}? It goes back to review.`)) return
    setBusy(true)
    setMsg('')
    try {
      const res = await skipGbpPending(brandId)
      setMsg(res.ok ? 'Skipped. The draft is back in review.' : `Not skipped: ${describe(res)}`)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Skip failed')
    } finally {
      setBusy(false)
      load()
    }
  }

  return (
    <section>
      <h2 className="mb-3 font-display text-xl font-semibold">Google Business post</h2>
      <div className="glass rounded-2xl border border-white/10 p-4">
        <p className="text-xs text-tx3">{name}</p>
        {!post && suggestion ? (
          <>
            <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-tx3">Suggested to go out</p>
            {data?.suggestion?.why ? <p className="mt-1 text-sm text-tx2">{data.suggestion.why}</p> : null}
            {suggestion.photo_url ? (
              <img
                src={suggestion.photo_url}
                alt="Photo for the suggested post"
                loading="lazy"
                className="mt-3 h-40 w-auto rounded-xl border border-white/10 object-cover"
              />
            ) : null}
            <p className="mt-3 font-medium">{suggestion.title}</p>
            <p className="mt-1 whitespace-pre-line text-sm">{suggestion.body}</p>
            <p className="mt-2 text-sm">
              {suggestion.cta}
              {suggestion.cta_url ? ` · ${suggestion.cta_url}` : ''}
            </p>
            <label className="mt-3 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={photoOk} onChange={(e) => setPhotoOk(e.target.checked)} />
              The photo shows what the text says
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button type="button" className={primary} disabled={busy || !photoOk} onClick={approveAndPublish}>
                Approve and publish (live)
              </button>
              {(data?.suggestion?.ready_count ?? 0) > 1 ? (
                <span className="text-xs text-tx3">{(data?.suggestion?.ready_count ?? 1) - 1} more ready on the Google Business Profile page</span>
              ) : null}
            </div>
          </>
        ) : !post ? (
          <p className="mt-2 text-sm text-tx3">
            {REASON[data?.reason ?? ''] ?? (data ? 'Nothing waiting.' : 'Loading...')}
          </p>
        ) : (
          <>
            {post.photo_url ? (
              <img
                src={post.photo_url}
                alt="Photo for today's post"
                loading="lazy"
                className="mt-3 h-40 w-auto rounded-xl border border-white/10 object-cover"
              />
            ) : (
              <p className="mt-3 text-sm text-red-300">No photo. This post cannot go out until one is attached on the draft.</p>
            )}
            <p className="mt-3 font-medium">{post.title}</p>
            <p className="mt-1 whitespace-pre-line text-sm">{post.body}</p>
            <p className="mt-2 text-sm">
              {post.cta}
              {post.cta_url ? ` · ${post.cta_url}` : ''}
            </p>
            {post.integrity_ok === false ? (
              <p className="mt-2 text-sm text-red-300">
                Blocked by the text check: {(post.integrity_violations ?? []).join(', ')}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className={primary}
                disabled={busy || !post.has_photo || post.integrity_ok === false}
                onClick={publish}
              >
                Publish to Google (live)
              </button>
              <button type="button" className={ghost} disabled={busy} onClick={skip}>
                Skip today
              </button>
            </div>
          </>
        )}
        {msg ? <p className="mt-3 text-sm text-tx2">{msg}</p> : null}
      </div>
    </section>
  )
}
