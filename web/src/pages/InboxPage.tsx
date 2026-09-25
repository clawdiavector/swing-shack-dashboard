import { BookMarked, Inbox, RotateCcw, X } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { BrandChip } from '../components/BrandChip'
import { useBrandScope } from '../components/BrandSwitch'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, StatCard, Tip } from '../components/ui'
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
} from '../lib/inboxCandidates'
import { sumCounts } from '../lib/mergeCounts'
import { useLoadGate } from '../lib/useLoadGate'
import { formatStamp } from '../lib/stamp'

function sourceLabel(tag: string): string {
  if (tag === 'holiday') return 'Holiday'
  if (tag === 'operator') return 'Operator'
  if (tag === 'interpreter') return 'Interpreter'
  return 'Scout'
}

function displayField(value?: string | null): string {
  const trimmed = value?.trim()
  return trimmed ? trimmed : '—'
}

function CandidateLabelRow({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
      <span className="shrink-0 text-tx3">{label}:</span>
      <span className="min-w-0 text-tx">{children}</span>
    </div>
  )
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
  onDone: () => void
  showBrandChip: boolean
  waitForReads?: () => Promise<void>
}) {
  const [dateVal, setDateVal] = useState(item.meta?.event_date || '')
  const [channel, setChannel] = useState(item.meta?.primary_channel || 'instagram')
  const [err, setErr] = useState('')
  const flags = item.meta?.flags || []
  const noLodge = lodgeDisabled(flags)
  const source = candidateSourceTag(item)

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
      else onDone()
      return
    }
    const result = await inboxAction(item.id, 'approve', '', mode)
    if (!result.ok) setErr(result.error || result.code || 'Action failed')
    else onDone()
  }

  return (
    <li className="rounded-2xl border border-bd bg-bg-2/40 px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="space-y-1">
            <CandidateLabelRow label="Title">{displayField(item.title)}</CandidateLabelRow>
            <CandidateLabelRow label="Pillar">{displayField(item.meta?.pillar)}</CandidateLabelRow>
            <CandidateLabelRow label="Angle">{displayField(item.meta?.angle)}</CandidateLabelRow>
            <CandidateLabelRow label="Why">
              {displayField(item.meta?.relevance_reason)}
            </CandidateLabelRow>
            <CandidateLabelRow label="Go-live">
              <input
                type="date"
                value={dateVal}
                onChange={(e) => setDateVal(e.target.value)}
                onBlur={() => void saveFields()}
                className="rounded-lg border border-bd bg-bg px-2 py-1 text-sm text-tx"
              />
            </CandidateLabelRow>
            <CandidateLabelRow label="Channel">
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                onBlur={() => void saveFields()}
                className="rounded-lg border border-bd bg-bg px-2 py-1 text-sm text-tx"
              >
                <option value="instagram">instagram</option>
                <option value="facebook">facebook</option>
                <option value="gbp">gbp</option>
              </select>
            </CandidateLabelRow>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <BrandChip brandId={item.brand_id} show={showBrandChip} />
            <Badge tone="mute">{sourceLabel(source)}</Badge>
          </div>
          <p className="text-xs text-tx3">Created {formatStamp(item.created_at)}</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Tip text={noLodge ? 'Set a go-live date before lodging.' : 'Book the moment and queue caption + image.'}>
          <button
            type="button"
            disabled={busy === item.id || noLodge}
            onClick={() => void act('lodge')}
            className="inline-flex items-center gap-1.5 rounded-full bg-ac px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-40"
          >
            <Inbox className="h-4 w-4" strokeWidth={2.5} />
            Lodge
          </button>
        </Tip>
        <button
          type="button"
          disabled={busy === item.id}
          onClick={() => void act('book')}
          className="inline-flex items-center gap-1 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold text-tx2"
        >
          <BookMarked className="h-4 w-4" strokeWidth={2} />
          Book only
        </button>
        <button
          type="button"
          disabled={busy === item.id}
          onClick={() => void act('reject')}
          className="inline-flex items-center gap-1 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold text-tx2"
        >
          <X className="h-4 w-4" />
          Reject
        </button>
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
  const { trackLoad, waitForLoad } = useLoadGate()

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

  return (
    <div className="space-y-6">
      <PageIntro here="/inbox" title="Inbox">
        Candidates waiting for a decision — lodge, book only, or reject.
      </PageIntro>

      <PartialBrandLoadStrip failures={failures} onRetry={load} />

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={Inbox} label="Pending" value={pending ?? '—'} hint="Candidates" tone="gold" />
        <StatCard icon={RotateCcw} label="Stale" value={stale ?? '—'} hint="Needs a decision" tone="mute" />
        <StatCard icon={BookMarked} label="Lodged today" value={approvedToday ?? '—'} hint="Booked today" tone="green" />
      </div>

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
            onDone={() => {
              setBusy('')
              load()
            }}
          />
        ))}
        {shown.length === 0 ? (
          <li className="rounded-2xl border border-dashed border-bd px-4 py-8 text-center text-sm text-tx3">
            No candidates in this filter.
          </li>
        ) : null}
      </ul>
    </div>
  )
}
