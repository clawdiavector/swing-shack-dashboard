import { BookMarked, Inbox, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import '../fun.css'
import { FunTile, Mascot } from '../components/fun'
import { burstAtPointer, burstConfetti } from '../lib/confetti'
import { BrandChip } from '../components/BrandChip'
import { useBrandScope } from '../components/BrandSwitch'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, Tip } from '../components/ui'
import {
  fetchInbox,
  inboxAction,
  inboxEdit,
  type InboxItem,
} from '../lib/api'
import { fanOutPayloads, type FanOutFailure } from '../lib/fanOut'
import {
  candidateSourceTag,
  filterInboxCandidates,
  lodgeDisabled,
  type InboxDateFilter,
  type InboxSourceFilter,
  isCandidateItem,
} from '../lib/inboxCandidates'
import { sumCounts } from '../lib/mergeCounts'
import { useLoadGate } from '../lib/useLoadGate'
import { formatStamp } from '../lib/stamp'
import { RENDER_MODE_LABELS, renderModeOf } from '../lib/postingWeek'

function sourceLabel(tag: string): string {
  if (tag === 'holiday') return 'Holiday'
  if (tag === 'operator') return 'Operator'
  if (tag === 'interpreter') return 'Interpreter'
  return 'Scout'
}

function CandidateCard({
  item,
  busy,
  onDone,
  showBrandChip,
  waitForReads,
}: {
  item: InboxItem
  busy: string
  onDone: (kind?: 'lodge' | 'book' | 'reject') => void
  showBrandChip: boolean
  waitForReads?: () => Promise<void>
}) {
  const [dateVal, setDateVal] = useState(item.meta?.event_date || '')
  const [channel, setChannel] = useState(item.meta?.primary_channel || 'instagram')
  const [err, setErr] = useState('')
  const flags = item.meta?.flags || []
  const noLodge = lodgeDisabled(flags)
  const source = candidateSourceTag(item)
  const pillar = item.meta?.pillar?.trim()
  const angle = item.meta?.angle?.trim()
  const relevanceReason = item.meta?.relevance_reason?.trim()
  const modePost = {
    calendar_id: item.meta?.calendar_id ?? '',
    title: item.title ?? '',
    stages: {},
    render_mode: item.meta?.render_mode as 'template' | 'oneshot' | undefined,
  }
  const inboxMode = renderModeOf(modePost)

  async function saveFields() {
    setErr('')
    const fields: Record<string, string> = {}
    if (dateVal) fields.event_date = dateVal
    if (channel) fields.primary_channel = channel
    const result = await inboxEdit(item.id, fields)
    if (!result.ok) {
      setErr(result.error || 'Save failed')
      return
    }
    if ((result.changed || []).length) onDone()
  }

  async function act(mode: 'lodge' | 'book' | 'reject') {
    setErr('')
    await waitForReads?.()
    if (mode === 'reject') {
      const result = await inboxAction(item.id, 'reject')
      if (!result.ok) setErr(result.error || 'Reject failed')
      else onDone('reject')
      return
    }
    const result = await inboxAction(item.id, 'approve', '', mode)
    if (!result.ok) setErr(result.error || result.code || 'Action failed')
    else onDone(mode)
  }

  return (
    <li className="glass fun-lift rounded-2xl border-[1.5px] border-white/10 px-4 py-3 backdrop-blur-xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-base font-semibold text-tx line-clamp-2">
            {item.title?.trim() ?? ''}
          </h3>
          {pillar ? (
            <p className="mt-1 text-xs text-tx3 line-clamp-1">{pillar}</p>
          ) : null}
          {angle ? (
            <p className="mt-0.5 text-xs text-tx2 line-clamp-1">{angle}</p>
          ) : null}
          {relevanceReason ? (
            <p className="mt-0.5 text-xs text-tx3 line-clamp-1">{relevanceReason}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <BrandChip brandId={item.brand_id} show={showBrandChip} />
            <Badge tone={inboxMode === 'oneshot' ? 'gold' : 'mute'}>{RENDER_MODE_LABELS[inboxMode]}</Badge>
            <Badge tone="mute">{sourceLabel(source)}</Badge>
          </div>
          <p className="text-right text-xs text-tx3">Created {formatStamp(item.created_at)}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-bd pt-2">
        <input
          type="date"
          value={dateVal}
          onChange={(e) => setDateVal(e.target.value)}
          onBlur={() => void saveFields()}
          className="rounded-full border border-bd bg-bg px-3 py-1 text-xs text-tx"
          aria-label="Go-live date"
        />
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          onBlur={() => void saveFields()}
          className="rounded-full border border-bd bg-bg px-3 py-1 text-xs text-tx"
          aria-label="Channel"
        >
          <option value="instagram">instagram</option>
          <option value="facebook">facebook</option>
          <option value="gbp">gbp</option>
        </select>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Tip text={noLodge ? 'Set a go-live date before lodging.' : 'Book the moment and queue caption + image.'}>
            <button
              type="button"
              disabled={busy === item.id || noLodge}
              onClick={() => void act('lodge')}
              className="fun-btn inline-flex items-center gap-1.5 rounded-full bg-ac px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-40"
            >
              <Inbox className="h-4 w-4" strokeWidth={2.5} />
              Lodge
            </button>
          </Tip>
          <button
            type="button"
            disabled={busy === item.id}
            onClick={() => void act('book')}
            className="fun-btn inline-flex items-center gap-1 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold text-tx2"
          >
            <BookMarked className="h-4 w-4" strokeWidth={2} />
            Book only
          </button>
          <button
            type="button"
            disabled={busy === item.id}
            onClick={() => void act('reject')}
            className="fun-btn inline-flex items-center gap-1 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold text-tx2"
          >
            <X className="h-4 w-4" />
            Reject
          </button>
        </div>
      </div>
      {err ? <p className="mt-2 text-sm text-red">{err}</p> : null}
    </li>
  )
}

export function InboxPage() {
  const { isAll, brandIds, scope } = useBrandScope()
  const [items, setItems] = useState<InboxItem[]>([])
  const [pending, setPending] = useState<number | null>(null)
  const [stale, setStale] = useState<number | null>(null)
  const [approvedToday, setApprovedToday] = useState<number | null>(null)
  const [source, setSource] = useState<InboxSourceFilter>('all')
  const [dateFilter, setDateFilter] = useState<InboxDateFilter>('all')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [failures, setFailures] = useState<FanOutFailure[]>([])
  const [cheer, setCheer] = useState('')
  const hadCandidates = useRef(false)
  const celebrated = useRef(false)
  const { trackLoad, waitForLoad } = useLoadGate()

  function sayCheer(text: string) {
    setCheer(text)
    setTimeout(() => setCheer((c) => (c === text ? '' : c)), 4500)
  }

  function load() {
    const run = async (): Promise<void> => {
      setFailures([])
      if (isAll) {
        const { payloads, failures: fails } = await fanOutPayloads(brandIds, (brandId) =>
          fetchInbox('pending', brandId),
        )
        setFailures(fails)
        const merged = payloads.flatMap(({ brandId, payload }) =>
          (payload.items || []).map((item) => ({
            ...item,
            brand_id: item.brand_id ?? brandId,
          })),
        )
        merged.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
        setItems(merged)
        const counts = sumCounts(payloads.map((p) => p.payload.counts))
        setPending(counts.pending ?? merged.length)
        setStale(counts.stale ?? 0)
        setApprovedToday(counts.approved_today ?? 0)
        setError('')
        return
      }
      const brandId = scope === 'all' ? 'swing-shack' : scope
      fetchInbox('pending', brandId)
        .then((payload) => {
          setItems(payload.items || [])
          setPending(payload.counts?.pending ?? 0)
          setStale(payload.counts?.stale ?? 0)
          setApprovedToday(payload.counts?.approved_today ?? 0)
        })
        .catch((err: Error) => setError(err.message))
    }
    trackLoad(run())
  }

  useEffect(load, [isAll, brandIds, scope, trackLoad])

  const shown = useMemo(
    () => filterInboxCandidates(items, source, dateFilter),
    [items, source, dateFilter],
  )
  // The fetch also returns drafts, which Approve drafts lists; count candidates only.
  const candidateCount = useMemo(() => items.filter(isCandidateItem).length, [items])
  useEffect(() => {
    if (candidateCount > 0) hadCandidates.current = true
    else if (hadCandidates.current && pending != null && !celebrated.current) {
      celebrated.current = true
      burstConfetti(window.innerWidth / 2, window.innerHeight / 3, 140)
    }
  }, [candidateCount, pending])
  const staleCandidateCount = useMemo(
    () => items.filter((i) => isCandidateItem(i) && i.sla_state === 'stale').length,
    [items],
  )

  return (
    <div className="space-y-6">
      <PageIntro here="/inbox" title="Inbox">
        Dates waiting for your call. Lodge it, book it only, or reject it.
      </PageIntro>

      <PartialBrandLoadStrip failures={failures} onRetry={load} />

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <FunTile label="Pending" value={pending == null ? '—' : candidateCount} hint="Candidates" tone="gold" />
        <FunTile label="Stale" value={stale == null ? '—' : staleCandidateCount} hint="Needs a decision" tone="violet" />
        <FunTile
          label="Lodged today"
          value={approvedToday ?? '—'}
          hint="Booked today"
          tone="green"
          dots={approvedToday != null ? { on: Math.min(approvedToday, 7) } : undefined}
        />
      </div>

      {cheer ? (
        <p className="fun-cheer" role="status">
          {cheer}
        </p>
      ) : null}

      {pending != null && candidateCount === 0 ? (
        <div className="fun-cleared" role="status">
          <Mascot tone="green" />
          <div>
            <strong>Inbox zero. Look at you!</strong>
            <span>No dates are waiting for your call.</span>
          </div>
        </div>
      ) : null}

      <FilterChips
        value={source}
        onChange={(v) => setSource(v as InboxSourceFilter)}
        options={[
          { id: 'all', label: 'All sources' },
          { id: 'scout', label: 'Scout' },
          { id: 'holiday', label: 'Holiday' },
          { id: 'interpreter', label: 'Interpreter' },
          { id: 'operator', label: 'Operator' },
        ]}
      />
      <FilterChips
        value={dateFilter}
        onChange={(v) => setDateFilter(v as InboxDateFilter)}
        options={[
          { id: 'all', label: 'Any date' },
          { id: 'has-date', label: 'Has date' },
          { id: 'no-date', label: 'No date' },
        ]}
      />

      <ul className="space-y-3">
        {shown.map((item) => (
          <CandidateCard
            key={item.id}
            item={item}
            busy={busy}
            showBrandChip={isAll}
            waitForReads={waitForLoad}
            onDone={(kind) => {
              setBusy('')
              if (kind === 'lodge') {
                burstAtPointer(60)
                sayCheer('Lodged. Caption and image are queued.')
              } else if (kind === 'book') {
                burstAtPointer(40)
                sayCheer('Booked. It’s on the calendar.')
              } else if (kind === 'reject') {
                sayCheer('Rejected. Off the list.')
              }
              load()
            }}
          />
        ))}
        {shown.length === 0 && candidateCount > 0 ? (
          <li className="fun-empty">
            <Mascot tone="blue" />
            <span>No candidates in this filter. Try All sources and Any date.</span>
          </li>
        ) : null}
      </ul>
    </div>
  )
}
