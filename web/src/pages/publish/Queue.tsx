import { Send } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FilterChips, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import {
  cancelPostizPost,
  fetchPostizOverview,
  reschedulePostizPost,
  type PostizOverview,
  type PostizQueueItem,
} from '../../lib/api'
import { matchQueueRow, pickQueueTitle } from '../../lib/publishCaption'
import { formatStamp } from '../../lib/stamp'

type QueueTab = 'drafts' | 'scheduled' | 'published' | 'failed'

const TAB_OPTIONS = [
  { id: 'drafts', label: 'Drafts' },
  { id: 'scheduled', label: 'Scheduled' },
  { id: 'published', label: 'Published' },
  { id: 'failed', label: 'Failed' },
]

function resolveTab(raw: string | null): QueueTab {
  if (raw === 'scheduled' || raw === 'published' || raw === 'failed') return raw
  return 'drafts'
}

function sliceCount(items: PostizQueueItem[] | undefined, total: number | undefined) {
  const n = items?.length ?? 0
  if (total != null && total > n) return `${n} of ${total}`
  return String(n)
}

export function Queue() {
  const [params, setParams] = useSearchParams()
  const tab = resolveTab(params.get('tab'))
  const highlightItem = params.get('item') || ''
  const highlightAsset = params.get('asset') || ''
  const [overview, setOverview] = useState<PostizOverview | null>(null)
  const [loadError, setLoadError] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const rowRefs = useRef<Record<string, HTMLLIElement | null>>({})

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const reload = useCallback(() => {
    setLoadError('')
    fetchPostizOverview()
      .then(setOverview)
      .catch((e: Error) => {
        setOverview(null)
        setLoadError(e.message || 'Could not load queue')
      })
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const rows = useMemo(() => {
    if (!overview) return []
    if (tab === 'scheduled') return overview.scheduled || []
    if (tab === 'published') return overview.published || []
    if (tab === 'drafts') return overview.queue || []
    return []
  }, [overview, tab])

  const highlightKey = useMemo(() => {
    if (!highlightItem && !highlightAsset) return null
    const idx = rows.findIndex((r) => matchQueueRow(r, highlightItem, highlightAsset))
    if (idx < 0) return 'missing'
    const row = rows[idx]
    return String(row.publish_id || row.item_id || idx)
  }, [rows, highlightItem, highlightAsset])

  useEffect(() => {
    if (!highlightKey || highlightKey === 'missing') return
    const el = rowRefs.current[highlightKey]
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    const p = new URLSearchParams(params)
    p.delete('item')
    p.delete('asset')
    setParams(p, { replace: true })
  }, [highlightKey, params, setParams])

  async function handleCancel(postId: string) {
    const reason = window.prompt('Cancel reason (optional):') ?? ''
    if (!window.confirm('Cancel this Postiz post? This reaches Postiz (live).')) return
    setActionMsg('')
    const { status, data } = await cancelPostizPost(postId, reason)
    if (data.partial) {
      setActionMsg('Postiz rejected cancel but local state may have moved (partial). Refresh and check Classic.')
    } else if (!data.ok && status >= 400) {
      setActionMsg(String(data.error || `Cancel failed (${status})`))
    } else {
      setActionMsg('Cancelled.')
      reload()
    }
  }

  async function handleReschedule(postId: string) {
    const scheduledAt = window.prompt('New time (ISO 8601, required):', '')?.trim()
    if (!scheduledAt) return
    if (!window.confirm('Reschedule on Postiz? This reaches Postiz (live).')) return
    setActionMsg('')
    const { status, data } = await reschedulePostizPost(postId, scheduledAt)
    if (data.partial) {
      setActionMsg('Postiz may disagree with local state (partial). Check Classic.')
    } else if (!data.ok && status >= 400) {
      setActionMsg(String(data.error || `Reschedule failed (${status})`))
    } else {
      setActionMsg('Rescheduled.')
      reload()
    }
  }

  const chipCounts = overview
    ? {
        drafts: sliceCount(overview.queue, overview.queue_total),
        scheduled: sliceCount(overview.scheduled, overview.scheduled_total),
        published: sliceCount(overview.published, overview.published_total),
        failed: '—',
      }
    : undefined

  return (
    <div className="space-y-6">
      <PageIntro icon={Send} here="/publish/queue" title="Publish queue">
        All brands — this queue is not brand-scoped. Rows come from flat publish files, not BrandSwitch.
      </PageIntro>

      <p className="rounded-2xl border border-bd/60 bg-bg2/40 px-4 py-3 text-sm text-tx2">
        <span className="font-semibold text-tx">All brands</span> — switching brand does not filter this list.
      </p>

      {overview?.dedup?.queue_hidden_shipped ? (
        <p className="text-xs text-tx3">
          {overview.dedup.queue_hidden_shipped} shipped item(s) still sit in the raw queue file (dedup hidden them here).
        </p>
      ) : null}

      {loadError ? (
        <p className="text-sm text-red">{loadError}</p>
      ) : null}
      {actionMsg ? <p className="text-sm text-yel">{actionMsg}</p> : null}

      <FilterChips
        options={TAB_OPTIONS.map((o) => ({
          ...o,
          label: chipCounts ? `${o.label} (${chipCounts[o.id as QueueTab]})` : o.label,
        }))}
        value={tab}
        onChange={setTab}
      />

      {highlightKey === 'missing' && (highlightItem || highlightAsset) ? (
        <p className="text-sm text-yel">
          That item is not in the first {tab === 'published' ? 20 : 30} rows — open{' '}
          <ClassicLink href="/?page=publish" label="publish queue" /> for the full list.
        </p>
      ) : null}

      {tab === 'failed' ? (
        <div className="rounded-2xl border border-dashed border-bd px-4 py-8 text-sm text-tx2">
          Not wired — publish failures are only summarised in the weekly report.{' '}
          <Link to="/results" className="text-ac underline">
            Open Results
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {rows.map((row, i) => {
            const key = String(row.publish_id || row.item_id || i)
            const postId = row.postiz_post_id ? String(row.postiz_post_id) : ''
            const selected = highlightKey === key
            const stamp = row.scheduled_date || row.publish_timestamp
            return (
              <li
                key={key}
                ref={(el) => {
                  rowRefs.current[key] = el
                }}
                className={`glass rounded-2xl border px-4 py-3 ${selected ? 'border-yel/50 ring-1 ring-yel/30' : 'border-white/10'}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-tx">{pickQueueTitle(row)}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-tx3">
                      {row.platform ? <Badge tone="blue">{String(row.platform)}</Badge> : null}
                      {row.status ? <Badge tone="mute">{String(row.status)}</Badge> : null}
                      {stamp ? <span>{formatStamp(String(stamp))}</span> : null}
                    </p>
                  </div>
                  {postId ? (
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Tip text="Reschedule on Postiz (live).">
                        <button
                          type="button"
                          onClick={() => handleReschedule(postId)}
                          className="glass-pill rounded-full border border-white/10 px-3 py-1.5 text-xs font-semibold hover:border-ac"
                        >
                          Reschedule…
                        </button>
                      </Tip>
                      <Tip text="Cancel on Postiz (live).">
                        <button
                          type="button"
                          onClick={() => handleCancel(postId)}
                          className="glass-pill rounded-full border border-white/10 px-3 py-1.5 text-xs font-semibold hover:border-ac"
                        >
                          Cancel
                        </button>
                      </Tip>
                    </div>
                  ) : null}
                </div>
              </li>
            )
          })}
          {!rows.length && !loadError ? (
            <li className="rounded-2xl border border-dashed border-bd px-4 py-8 text-sm text-tx3">
              Nothing in this lane yet.
            </li>
          ) : null}
        </ul>
      )}

      <ClassicLink href="/?page=publish" label="publish queue" />
    </div>
  )
}
