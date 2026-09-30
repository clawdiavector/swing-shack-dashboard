import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Check,
  X,
  Clock,
  Send,
  Calendar,
  AlertTriangle,
} from 'lucide-react'
import { PageIntro } from '../components/chrome'
import { Badge } from '../components/ui'
import { useBrand } from '../components/BrandSwitch'

function CardSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="glass rounded-2xl border border-white/10 p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-tx-3">{title}</h3>
      {children}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PublishStatus =
  | 'READY_TO_STAGE'
  | 'STAGED_AS_DRAFT'
  | 'READY_TO_PUBLISH'
  | 'SCHEDULED'
  | 'PUBLISHED'
  | 'PUBLISH_FAILED'
  | 'CANCELLED'

type PublishHistoryItem = {
  action: string
  actor: string
  at: string
  from: string | null
  to: string | null
  result?: Record<string, unknown>
}

type PublishRecord = {
  publish_id: string
  brand_id: string
  brief_id: string
  status: PublishStatus
  title?: string
  article_title?: string
  cms_target?: string
  cms_post_id?: number | null
  cms_preview_url?: string | null
  cms_edit_url?: string | null
  cms_live_url?: string | null
  cms_slug?: string | null
  scheduled_publish_at?: string | null
  scheduled_timezone?: string | null
  approved_by?: string
  approved_at?: string
  approved_revision_id?: string
  approved_content_hash?: string
  history: PublishHistoryItem[]
  checks: {
    internal_links_passed: boolean | null
    internal_links_blocked: Array<{ url: string; status: number }>
    stock_price_passed: boolean | null
    stock_price_blockers: string[]
    seo_metadata_written: string[]
    seo_metadata_unsupported: string[]
    featured_image_status: string | null
  }
  created_at?: string
  updated_at?: string
}

type QueueItem = PublishRecord

type PublishTarget = {
  brand_id: string
  cms_target: string
  cms_kind: string
  enabled: boolean
  timezone: string
  seo_metadata_supported: boolean
  scheduling_supported: boolean
}

const STATUS_TONE: Record<PublishStatus, 'mute' | 'gold' | 'green' | 'red' | 'blue'> = {
  READY_TO_STAGE: 'gold',
  STAGED_AS_DRAFT: 'blue',
  READY_TO_PUBLISH: 'blue',
  SCHEDULED: 'blue',
  PUBLISHED: 'green',
  PUBLISH_FAILED: 'red',
  CANCELLED: 'mute',
}

const STATUS_LABEL: Record<PublishStatus, string> = {
  READY_TO_STAGE: 'READY TO STAGE',
  STAGED_AS_DRAFT: 'STAGED AS DRAFT',
  READY_TO_PUBLISH: 'READY TO PUBLISH',
  SCHEDULED: 'SCHEDULED',
  PUBLISHED: 'PUBLISHED',
  PUBLISH_FAILED: 'PUBLISH FAILED',
  CANCELLED: 'CANCELLED',
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PublishLongForm() {
  const { brandId, publishId } = useParams()
  const { brandId: activeBrandId } = useBrand()
  const effectiveBrand = brandId || activeBrandId || 'stick'

  const [queue, setQueue] = useState<QueueItem[]>([])
  const [record, setRecord] = useState<PublishRecord | null>(null)
  const [targets, setTargets] = useState<Record<string, PublishTarget>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmPublish, setConfirmPublish] = useState(false)
  const [scheduleDate, setScheduleDate] = useState('')
  const [error, setError] = useState<string | null>(null)

  const brand = effectiveBrand

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [queueRes, targetsRes] = await Promise.all([
        fetch(`/api/publish/v1/queue/${brand}`, { credentials: 'include' }),
        fetch('/api/publish/v1/targets', { credentials: 'include' }),
      ])
      const queueData = await queueRes.json()
      const targetsData = await targetsRes.json()
      setQueue(queueData.queue || [])
      setTargets(targetsData.targets || {})
      if (publishId) {
        const detailRes = await fetch(
          `/api/publish/v1/${brand}/${publishId}`,
          { credentials: 'include' },
        )
        const detail = await detailRes.json()
        if (detail.ok) setRecord(detail.record)
        else setError(detail.error || 'publish record not found')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [brand, publishId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const runAction = useCallback(
    async (action: 'stage' | 'publish' | 'cancel-schedule' | 'cancel' | 'schedule', extra?: Record<string, unknown>) => {
      if (!record) return
      const key = `${action}:${record.publish_id}`
      setBusy(key)
      setError(null)
      try {
        const res = await fetch(`/api/publish/v1/${brand}/${record.publish_id}/${action}`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(extra || {}),
        })
        const data = await res.json()
        if (!data.ok) {
          setError(`${data.code || 'error'}: ${data.error || ''}`)
        } else {
          await refresh()
          setConfirmPublish(false)
        }
      } catch (e) {
        setError(String(e))
      } finally {
        setBusy(null)
      }
    },
    [brand, record, refresh],
  )

  if (loading && !queue.length && !record) {
    return (
      <PageIntro here="/publish" title="Publish — long-form articles">
          Loading…
        </PageIntro>
  )
  }

  if (publishId && record) {
    return (
      <PublishDetailView
          record={record}
          target={targets[record.brand_id]}
          busy={busy}
          confirmPublish={confirmPublish}
          setConfirmPublish={setConfirmPublish}
          scheduleDate={scheduleDate}
          setScheduleDate={setScheduleDate}
          error={error}
          onBack={() => {
            setRecord(null)
          }}
          onStage={() => runAction('stage')}
          onSchedule={() => {
            if (!scheduleDate) {
              setError('schedule date required')
              return
            }
            runAction('schedule', {
              publish_at: scheduleDate,
              timezone: targets[record.brand_id]?.timezone || 'Africa/Johannesburg',
            })
          }}
          onCancelSchedule={() => runAction('cancel-schedule')}
          onPublish={() => runAction('publish')}
          onCancel={() => runAction('cancel')}
        />
  )
  }

  return (
    <PublishQueueView queue={queue} targets={targets} brand={brand} error={error} />
  )
}

// ---------------------------------------------------------------------------
// Queue view
// ---------------------------------------------------------------------------

function PublishQueueView({
  queue,
  targets,
  brand,
  error,
}: {
  queue: QueueItem[]
  targets: Record<string, PublishTarget>
  brand: string
  error: string | null
}) {
  const target = targets[brand]
  const grouped = useMemo(() => {
    const g: Record<PublishStatus, QueueItem[]> = {
      READY_TO_STAGE: [],
      STAGED_AS_DRAFT: [],
      READY_TO_PUBLISH: [],
      SCHEDULED: [],
      PUBLISHED: [],
      PUBLISH_FAILED: [],
      CANCELLED: [],
    }
    for (const q of queue) {
      const s = (q.status || 'READY_TO_STAGE') as PublishStatus
      g[s].push(q)
    }
    return g
  }, [queue])

  return (
    <div className="space-y-6">
      <PageIntro
        here="/publish"
        title={
          <span>
            Publish — long-form articles{' '}
            <span className="text-tx3 font-normal">
              {target
                ? `· Brand: ${brand} · Target: ${target.cms_target} · ${target.enabled ? 'ENABLED' : 'DISABLED'}`
                : `· Brand: ${brand} · No target configured`}
            </span>
          </span>
        }
      >
        Long-form CMS articles only. V1 supports one type at a time — Writer V1
        output → Review V1.1 approval → here. Approval gates every CMS write.
      </PageIntro>

      {error ? (
        <CardSection title="Error">
          <div className="text-red text-sm font-mono">{error}</div>
        </CardSection>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <StatusGroup
          label="READY TO STAGE"
          items={grouped.READY_TO_STAGE}
          brand={brand}
          targets={targets}
          empty="Nothing waiting for staging. Approve a Review first."
        />
        <StatusGroup
          label="STAGED AS DRAFT"
          items={grouped.STAGED_AS_DRAFT}
          brand={brand}
          targets={targets}
          empty="No drafts in CMS."
        />
        <StatusGroup
          label="SCHEDULED"
          items={grouped.SCHEDULED}
          brand={brand}
          targets={targets}
          empty="No scheduled posts."
        />
        <StatusGroup
          label="PUBLISHED"
          items={grouped.PUBLISHED}
          brand={brand}
          targets={targets}
          empty="No live posts yet."
        />
      </div>

      {grouped.PUBLISH_FAILED.length > 0 ? (
        <StatusGroup
          label="PUBLISH FAILED"
          items={grouped.PUBLISH_FAILED}
          brand={brand}
          targets={targets}
          empty=""
        />
      ) : null}
      {grouped.CANCELLED.length > 0 ? (
        <StatusGroup
          label="CANCELLED"
          items={grouped.CANCELLED}
          brand={brand}
          targets={targets}
          empty=""
        />
      ) : null}
    </div>
  )
}

function StatusGroup({
  label,
  items,
  brand,
  targets,
  empty,
}: {
  label: string
  items: QueueItem[]
  brand: string
  targets: Record<string, PublishTarget>
  empty: string
}) {
  return (
    <CardSection title={`${label} (${items.length})`}>
      {items.length === 0 ? (
        <div className="text-sm text-tx-3">{empty}</div>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <PublishQueueRow key={it.publish_id} item={it} brand={brand} target={targets[brand]} />
          ))}
        </div>
      )}
    </CardSection>
  )
}

function PublishQueueRow({ item, target: _target }: { item: QueueItem; brand: string; target?: PublishTarget }) {
  const tone = STATUS_TONE[item.status] || 'mute'
  return (
    <Link
      to={`/publish/long-form/${item.publish_id}`}
      className="glass block w-full rounded-2xl border border-white/10 p-4 text-left transition-colors hover:border-yel/40"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge tone={tone}>{STATUS_LABEL[item.status]}</Badge>
            <span className="text-sm text-tx-3">· {item.brand_id}</span>
          </div>
          <div className="mt-2 truncate text-base font-semibold text-tx">
            {item.article_title || item.title || item.brief_id}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-tx-3">
            <span>brief: <code className="text-tx-2">{item.brief_id}</code></span>
            <span>target: <code className="text-tx-2">{item.cms_target || '—'}</code></span>
            {item.cms_post_id ? (
              <span>cms id: <code className="text-tx-2">{item.cms_post_id}</code></span>
            ) : null}
            {item.scheduled_publish_at ? (
              <span>scheduled: <code className="text-tx-2">{item.scheduled_publish_at} ({item.scheduled_timezone})</code></span>
            ) : null}
          </div>
        </div>
        {item.cms_preview_url ? (
          <a
            href={item.cms_preview_url}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-white/10 px-3 py-1 text-xs hover:border-ac hover:text-ac"
            onClick={(e) => e.stopPropagation()}
          >
            OPEN PREVIEW ↗
          </a>
        ) : null}
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Detail view
// ---------------------------------------------------------------------------

function PublishDetailView({
  record,
  target,
  busy,
  confirmPublish,
  setConfirmPublish,
  scheduleDate,
  setScheduleDate,
  error,
  onBack,
  onStage,
  onSchedule,
  onCancelSchedule,
  onPublish,
  onCancel,
}: {
  record: PublishRecord
  target?: PublishTarget
  busy: string | null
  confirmPublish: boolean
  setConfirmPublish: (v: boolean) => void
  scheduleDate: string
  setScheduleDate: (v: string) => void
  error: string | null
  onBack: () => void
  onStage: () => void
  onSchedule: () => void
  onCancelSchedule: () => void
  onPublish: () => void
  onCancel: () => void
}) {
  const tone = STATUS_TONE[record.status] || 'mute'
  const isBusy = (action: string) => busy === `${action}:${record.publish_id}`

  const allowedActions = useMemo(() => {
    const a: string[] = []
    if (record.status === 'READY_TO_STAGE' || record.status === 'STAGED_AS_DRAFT') {
      a.push('stage')
    }
    if (record.status === 'STAGED_AS_DRAFT' || record.status === 'READY_TO_PUBLISH') {
      a.push('publish')
      if (target?.scheduling_supported) a.push('schedule')
    }
    if (record.status === 'SCHEDULED') a.push('cancel-schedule')
    if (record.status !== 'PUBLISHED' && record.status !== 'CANCELLED') a.push('cancel')
    return a
  }, [record.status, target])

  return (
    <div className="space-y-6">
      <PageIntro
        here="/publish"
        title={
          <span>
            Publish — long-form articles{' '}
            <span className="text-tx3 font-normal">
              <button onClick={onBack} className="text-yel hover:underline">
                · BACK TO QUEUE
              </button>
            </span>
          </span>
        }
      >
        Every CMS write here is gated by an APPROVED_FOR_PUBLISHING Review
        record and locked to the article body that was approved.
      </PageIntro>

      <CardSection title="Article + publish state">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={tone}>{STATUS_LABEL[record.status]}</Badge>
            <span className="text-sm text-tx-3">· {record.brand_id}</span>
          </div>
          <div className="text-xl font-semibold text-tx">
            {record.article_title || record.brief_id}
          </div>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-2">
            <KV label="Brief ID" value={<code>{record.brief_id}</code>} />
            <KV label="CMS target" value={<code>{record.cms_target || '—'}</code>} />
            <KV label="CMS post id" value={record.cms_post_id ?? '—'} />
            <KV label="Approved by" value={record.approved_by || '—'} />
            <KV label="Approved at" value={record.approved_at || '—'} />
            <KV label="Approved revision" value={<code className="text-xs">{record.approved_revision_id || '—'}</code>} />
            <KV label="Approved hash" value={<code className="text-xs">{(record.approved_content_hash || '').slice(0, 24)}…</code>} />
            <KV label="Scheduled" value={record.scheduled_publish_at ? `${record.scheduled_publish_at} (${record.scheduled_timezone})` : '—'} />
          </dl>
          {record.cms_preview_url ? (
            <div className="flex flex-wrap gap-2 pt-2">
              <a
                href={record.cms_preview_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-full border border-white/10 px-3 py-1.5 text-xs hover:border-ac hover:text-ac"
              >
                OPEN CMS PREVIEW ↗
              </a>
              {record.cms_edit_url ? (
                <a
                  href={record.cms_edit_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border border-white/10 px-3 py-1.5 text-xs hover:border-ac hover:text-ac"
                >
                  OPEN CMS EDITOR ↗
                </a>
              ) : null}
              {record.cms_live_url ? (
                <a
                  href={record.cms_live_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border border-white/10 px-3 py-1.5 text-xs hover:border-ac hover:text-ac"
                >
                  OPEN LIVE URL ↗
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      </CardSection>

      <CardSection title="Pre-publish checks">
        <ChecksPanel checks={record.checks} />
      </CardSection>

      <CardSection title="Actions">
        <div className="flex flex-wrap items-center gap-2">
          {allowedActions.includes('stage') ? (
            <PillButton
              icon={Send}
              tone="ghost"
              disabled={isBusy('stage')}
              onClick={onStage}
            >
              {record.cms_post_id ? 'UPDATE STAGED DRAFT' : 'SEND TO CMS AS DRAFT'}
            </PillButton>
          ) : null}

          {allowedActions.includes('publish') ? (
            <PillButton
              icon={Check}
              tone="green"
              disabled={isBusy('publish') || !record.cms_post_id || confirmPublish}
              onClick={() => setConfirmPublish(true)}
            >
              PUBLISH NOW
            </PillButton>
          ) : null}

          {allowedActions.includes('schedule') ? (
            <div className="flex items-center gap-2">
              <input
                type="datetime-local"
                value={scheduleDate}
                onChange={(e) => setScheduleDate(e.target.value)}
                className="glass-pill rounded-full border border-white/10 px-3 py-1.5 text-sm"
              />
              <PillButton
                icon={Calendar}
                tone="ghost"
                disabled={isBusy('schedule') || !scheduleDate}
                onClick={onSchedule}
              >
                SCHEDULE
              </PillButton>
            </div>
          ) : null}

          {allowedActions.includes('cancel-schedule') ? (
            <PillButton
              icon={Clock}
              tone="ghost"
              disabled={isBusy('cancel-schedule')}
              onClick={onCancelSchedule}
            >
              CANCEL SCHEDULE
            </PillButton>
          ) : null}

          {allowedActions.includes('cancel') ? (
            <PillButton
              icon={X}
              tone="ghost"
              disabled={isBusy('cancel')}
              onClick={onCancel}
            >
              CANCEL
            </PillButton>
          ) : null}
        </div>

        {confirmPublish ? (
          <div className="glass mt-4 rounded-2xl border border-yel/40 p-4">
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-yel" />
              <span className="font-semibold text-yel">Confirm publish</span>
            </div>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-2">
              <KV label="Brand" value={record.brand_id} />
              <KV label="Site" value={record.cms_target} />
              <KV label="Title" value={record.article_title || record.brief_id} />
              <KV label="Revision" value={<code className="text-xs">{record.approved_revision_id || '—'}</code>} />
              <KV label="Slug" value={record.cms_slug || <span className="text-tx-3">(auto)</span>} />
              <KV label="CMS draft id" value={record.cms_post_id || '—'} />
              <KV label="Approved by" value={record.approved_by || '—'} />
              <KV label="Approved at" value={record.approved_at || '—'} />
              <KV label="Destination URL" value={record.cms_preview_url || '—'} />
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <PillButton icon={Check} tone="green" disabled={isBusy('publish')} onClick={onPublish}>
                CONFIRM PUBLISH
              </PillButton>
              <PillButton tone="ghost" onClick={() => setConfirmPublish(false)}>
                NEVERMIND
              </PillButton>
            </div>
          </div>
        ) : null}
      </CardSection>

      {error ? (
        <CardSection title="Error">
          <div className="text-sm font-mono text-red">{error}</div>
        </CardSection>
      ) : null}

      <CardSection title={`History (${record.history.length})`}>
        <ol className="space-y-1 text-sm">
          {record.history.map((h, idx) => (
            <li key={idx} className="flex flex-wrap items-center gap-2 font-mono text-xs">
              <span className="text-tx-3">{h.at}</span>
              <Badge tone="mute">{h.action}</Badge>
              <span className="text-tx-3">{h.from || '∅'} → {h.to || '∅'}</span>
              <span className="text-tx-3">· by {h.actor}</span>
            </li>
          ))}
        </ol>
      </CardSection>
    </div>
  )
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="text-tx-3 text-xs uppercase tracking-wide">{label}</dt>
      <dd className="text-tx text-sm">{value}</dd>
    </div>
  )
}

function ChecksPanel({ checks }: { checks: PublishRecord['checks'] }) {
  return (
    <div className="space-y-3">
      <CheckRow
        label="Internal links"
        passed={checks.internal_links_passed}
        blocked={checks.internal_links_blocked}
        formatBlocked={(b) => `${b.url} → HTTP ${b.status}`}
      />
      <CheckRow
        label="Stock / price safety"
        passed={checks.stock_price_passed}
        blocked={checks.stock_price_blockers}
        formatBlocked={(b) => String(b)}
      />
      <div className="text-sm">
        <span className="text-tx-3">SEO metadata written: </span>
        {checks.seo_metadata_written.length === 0 ? (
          <span className="text-tx-3">none</span>
        ) : (
          checks.seo_metadata_written.map((k) => (
            <Badge key={k} tone="green">{k}</Badge>
          ))
        )}
        {checks.seo_metadata_unsupported.length > 0 ? (
          <span className="ml-2 text-tx-3">
            · unsupported: {checks.seo_metadata_unsupported.map((k) => <Badge key={k} tone="mute">{k}</Badge>)}
          </span>
        ) : null}
      </div>
      <div className="text-sm">
        <span className="text-tx-3">Featured image: </span>
        {checks.featured_image_status === 'UPLOADED' ? (
          <Badge tone="green">UPLOADED</Badge>
        ) : checks.featured_image_status === 'MISSING_NOT_REQUIRED' ? (
          <Badge tone="mute">NOT SET (staged without)</Badge>
        ) : (
          <Badge tone="gold">NOT SET</Badge>
        )}
      </div>
    </div>
  )
}

function CheckRow<T>({
  label,
  passed,
  blocked,
  formatBlocked,
}: {
  label: string
  passed: boolean | null
  blocked: T[]
  formatBlocked: (b: T) => string
}) {
  return (
    <div className="text-sm">
      <span className="text-tx-3">{label}: </span>
      {passed === true ? <Badge tone="green">PASSED</Badge> : null}
      {passed === false ? <Badge tone="red">BLOCKED</Badge> : null}
      {passed === null ? <Badge tone="gold">NOT YET RUN</Badge> : null}
      {blocked.length > 0 ? (
        <ul className="ml-2 mt-1 list-disc pl-5 text-xs text-tx-3">
          {blocked.map((b, idx) => (
            <li key={idx} className="font-mono">
              {formatBlocked(b)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

// Local Button (plain HTML <button>) since the shared Button component is
// a styled Link wrapper and doesn't accept onClick/disabled in the form
// needed here.
function PillButton({
  children,
  icon: Icon,
  tone = 'ghost',
  disabled = false,
  onClick,
}: {
  children: React.ReactNode
  icon?: React.ComponentType<{ className?: string }>
  tone?: 'ghost' | 'green'
  disabled?: boolean
  onClick?: () => void
}) {
  const cls =
    tone === 'green'
      ? 'inline-flex items-center gap-1.5 rounded-full bg-ac px-4 py-2 text-sm font-semibold text-bg transition-colors hover:bg-ac/90 disabled:opacity-50'
      : 'inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-tx transition-colors hover:border-ac hover:text-ac disabled:opacity-50'
  return (
    <button type="button" disabled={disabled} className={cls} onClick={onClick}>
      {Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  )
}
