import { CalendarDays, ChevronLeft, ChevronRight, Lightbulb, Map, Send } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, MonthGrid, PageIntro } from '../components/chrome'
import { Badge, Button, ClassicLink, IconTile, QueueItem, StatCard, Tip } from '../components/ui'
import {
  duplicateScheduledAsset,
  fetchCalendarMonth,
  fetchIntelCalendar,
  fetchToday,
  rescheduleAsset,
  transitionCalendarRecord,
  unscheduleAsset,
  type CalendarItem,
  type TodayPanel,
} from '../lib/api'
import { dayInMonth, formatDateStamp, isoDate, parseIsoDateParam } from '../lib/stamp'
import { toolTo } from '../lib/tools'

type Parked = {
  key: string
  day: number
  title: string
  badge: string
  to: string
  stamp?: string
  stampKind?: string
  source?: string
  color?: string
  assetId?: string
  campaignId?: string
  platform?: string
  calendarId?: string
  item?: CalendarItem
  meta?: string
}

function momentStampKind(type?: string): 'holiday' | 'moment' | 'campaign' {
  if (/holiday/i.test(type || '')) return 'holiday'
  if ((type || '').toLowerCase() === 'campaign') return 'campaign'
  return 'moment'
}

function typeChipLabel(type?: string) {
  const k = momentStampKind(type)
  if (k === 'holiday') return 'Public holiday'
  if (k === 'campaign') return 'Campaign'
  return type ? type.replace(/_/g, ' ') : 'Moment'
}

function scoreLine(label: string, value?: number | string | null) {
  if (value === undefined || value === null || value === '') return null
  return (
    <span key={label}>
      {label}: {String(value)}
    </span>
  )
}

function MomentPanel({
  item,
  onClose,
  onDismiss,
}: {
  item: CalendarItem
  onClose: () => void
  onDismiss: () => void
}) {
  const eventDate = item.event_date || item.campaign_start
  const dateLine = eventDate
    ? `${formatDateStamp(eventDate)}${item.event_end ? ` – ${formatDateStamp(item.event_end)}` : ''}`
    : '—'
  const planStart = item.planning_start || item.lead_time_schedule?.planning_start
  const scores = [
    scoreLine('Commercial', item.commercial_relevance),
    scoreLine('Audience', item.audience_relevance),
    scoreLine('Brand', item.brand_relevance),
    scoreLine('Timeliness', item.timeliness),
    scoreLine('Confidence', item.confidence),
  ].filter(Boolean)
  const sourceUrl = item.source_urls?.[0]
  const buildDate = eventDate || isoDate(new Date())
  const buildId = item.calendar_id || ''

  return (
    <aside className="glass sticky top-4 max-h-[calc(100vh-6rem)] space-y-4 overflow-y-auto rounded-2xl border border-white/10 p-4 lg:col-span-1">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-display text-lg font-semibold leading-snug">{item.title || 'Untitled'}</h2>
        <Tip text="Close the moment panel. Keeps the day you picked.">
          <button type="button" className="text-xs text-tx3 hover:text-tx" onClick={onClose}>
            Close
          </button>
        </Tip>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="mute">{typeChipLabel(item.type)}</Badge>
        {item.status ? <Badge tone="gold">{item.status}</Badge> : null}
      </div>
      <p className="text-sm text-tx2">{dateLine}</p>
      {item.relevance_reason ? (
        <div>
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Why this brand</p>
          <p className="mt-1 text-sm text-tx2">{item.relevance_reason}</p>
          {scores.length ? (
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-tx3">{scores}</p>
          ) : null}
        </div>
      ) : scores.length ? (
        <div>
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Scores</p>
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-tx3">{scores}</p>
        </div>
      ) : null}
      {item.suggested_angles?.length ? (
        <div>
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Suggested angles</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-tx2">
            {item.suggested_angles.map((angle) => (
              <li key={angle}>{angle}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {item.pillars?.length ? (
        <div>
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Pillars</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {item.pillars.map((pillar) =>
              item.colour ? (
                <span
                  key={pillar}
                  className="rounded-full px-2.5 py-0.5 text-xs font-semibold text-bg"
                  style={{ backgroundColor: item.colour }}
                >
                  {pillar}
                </span>
              ) : (
                <Badge key={pillar} tone="mute">
                  {pillar}
                </Badge>
              ),
            )}
          </div>
        </div>
      ) : null}
      {planStart || item.lead_time_days != null ? (
        <div>
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Plan by</p>
          <p className="mt-1 text-sm text-tx2">
            {planStart
              ? `Start planning by ${formatDateStamp(planStart)}`
              : item.lead_time_days != null
                ? `${item.lead_time_days} days lead time`
                : ''}
          </p>
        </div>
      ) : null}
      {item.source_title || item.source_domain || sourceUrl ? (
        <div>
          <p className="text-xs font-semibold tracking-wide text-tx3 uppercase">Source</p>
          {item.source_title ? <p className="mt-1 text-sm font-semibold text-tx">{item.source_title}</p> : null}
          {item.source_domain ? <p className="text-xs text-tx3">{item.source_domain}</p> : null}
          {sourceUrl ? (
            <Tip text="Open the source link in a new tab.">
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 block text-sm text-ac underline"
              >
                {sourceUrl}
              </a>
            </Tip>
          ) : null}
          <p className="mt-2 text-xs font-semibold">
            {item.trusted_for_planning === true ? (
              <span className="text-ac">Trusted for planning</span>
            ) : (
              <span className="text-yel">Watchlist — check before you build</span>
            )}
          </p>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2 pt-2">
        <Button
          to={`/create/post?date=${encodeURIComponent(buildDate)}&calendar_item_id=${encodeURIComponent(buildId)}`}
          icon={Send}
          tip="Open Build a post with this day and calendar moment id prefilled."
        >
          Build a post for this day
        </Button>
        <Tip text="Remove this moment from the active calendar list.">
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-red hover:text-red"
          >
            Dismiss
          </button>
        </Tip>
        <ClassicLink href="/?page=calendar" label="calendar" />
      </div>
    </aside>
  )
}

function daysInMonth(year: number, month0: number) {
  return new Date(year, month0 + 1, 0).getDate()
}

export function CalendarPage() {
  const { brandId } = useBrand()
  const [params, setParams] = useSearchParams()
  const cursor = useMemo(() => parseIsoDateParam(params.get('date')), [params])
  const year = cursor.getFullYear()
  const month0 = cursor.getMonth()
  const selected = cursor.getDate()
  const now = new Date()
  const todayDay = now.getDate()
  const todayMonth0 = now.getMonth()
  const todayYear = now.getFullYear()

  const [data, setData] = useState<TodayPanel | null>(null)
  const [parked, setParked] = useState<Parked[]>([])
  const [loadError, setLoadError] = useState('')
  const [noCalendarConfig, setNoCalendarConfig] = useState(false)
  const [moveFor, setMoveFor] = useState<string | null>(null)
  const [moveDate, setMoveDate] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const monthLabel = new Intl.DateTimeFormat('en-ZA', { month: 'long', year: 'numeric' }).format(
    cursor,
  )
  const monthName = new Intl.DateTimeFormat('en-ZA', { month: 'long' }).format(cursor)
  const selectedIso = isoDate(new Date(year, month0, selected))
  const monthStart = isoDate(new Date(year, month0, 1))
  const monthEnd = isoDate(new Date(year, month0, daysInMonth(year, month0)))
  const monthDays = daysInMonth(year, month0)

  const setCursorIso = useCallback(
    (iso: string) => {
      const p = new URLSearchParams(params)
      p.set('date', iso)
      p.delete('id')
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const selectedId = params.get('id') || ''
  const closeMoment = useCallback(() => {
    const p = new URLSearchParams(params)
    p.delete('id')
    setParams(p, { replace: true })
  }, [params, setParams])

  const selectDay = useCallback(
    (day: number) => {
      setCursorIso(isoDate(new Date(year, month0, day)))
    },
    [year, month0, setCursorIso],
  )

  const shiftMonth = useCallback(
    (delta: number) => {
      const target = new Date(year, month0 + delta, 1)
      const ty = target.getFullYear()
      const tm = target.getMonth()
      const dim = daysInMonth(ty, tm)
      setCursorIso(isoDate(new Date(ty, tm, Math.min(selected, dim))))
    },
    [year, month0, selected, setCursorIso],
  )

  const goToday = useCallback(() => {
    setCursorIso(isoDate(new Date()))
  }, [setCursorIso])

  useEffect(() => {
    let gone = false
    setLoadError('')
    setNoCalendarConfig(false)
    fetchToday(brandId)
      .then(async (panel) => {
        if (gone) return
        setData(panel)
        const brand = brandId || panel.active_brand_id || ''
        const fromCards: Parked[] = (panel.cards || [])
          .map((card) => {
            const day = dayInMonth(card.stamp || card.updatedAt || card.createdAt, year, month0)
            if (!day) return null
            return {
              key: `card:${card.kind}:${card.id}`,
              day,
              title: card.title,
              badge: card.label || card.kind,
              to: `/review/${encodeURIComponent(card.id)}`,
              stamp: card.stamp || card.updatedAt,
              stampKind: card.stampKind,
              source: 'card',
            } satisfies Parked
          })
          .filter((row) => row != null) as Parked[]

        const merged: Parked[] = [...fromCards]
        const seen = new Set(merged.map((r) => r.key))

        if (brand) {
          const [view, intel] = await Promise.all([
            fetchCalendarMonth(brand, monthStart, monthEnd),
            fetchIntelCalendar(brand, monthStart, monthDays).catch(() => ({ ok: false, days: [] })),
          ])
          if (gone) return

          if (view.status === 404 && (view.error || '').includes('calendar_config')) {
            setNoCalendarConfig(true)
          }

          const fromCal: Parked[] = (view.items || [])
            .map((item) => {
              const day = dayInMonth(item.event_date || item.campaign_start, year, month0)
              if (!day) return null
              const date = item.event_date || item.campaign_start || selectedIso
              const stampKind = momentStampKind(item.type)
              return {
                key: `cal:${item.calendar_id || item.title}`,
                day,
                title: item.title || 'Untitled',
                badge: item.status || item.type || 'moment',
                to: `?date=${date}&id=${encodeURIComponent(item.calendar_id || '')}`,
                stamp: item.event_date || item.campaign_start,
                stampKind,
                source: 'moment',
                calendarId: item.calendar_id,
                item,
              } satisfies Parked
            })
            .filter((row) => row != null) as Parked[]

          for (const row of fromCal) {
            if (seen.has(row.key)) continue
            seen.add(row.key)
            merged.push(row)
          }

          for (const dayRow of intel.days || []) {
            const day = dayInMonth(dayRow.date, year, month0)
            if (!day) continue
            for (const slot of dayRow.slots || []) {
              const aid = slot.assetId || ''
              const key = `slot:${aid || slot.name}:${dayRow.date}`
              if (seen.has(key)) continue
              seen.add(key)
              merged.push({
                key,
                day,
                title: slot.name || slot.caption?.slice(0, 80) || 'Scheduled',
                badge: slot.pillar || slot.platform || slot.source || 'scheduled',
                to: aid ? `/review/${encodeURIComponent(aid)}` : toolTo('calendar', { date: dayRow.date }),
                stamp: slot.scheduledFor,
                stampKind: 'scheduled',
                source: slot.source || 'slot',
                color: slot.color,
                assetId: aid,
                campaignId: slot.campaignId,
                platform: slot.platform,
                meta: [slot.platform, slot.caption?.slice(0, 90)].filter(Boolean).join(' · '),
              })
            }
          }
        }

        setParked(merged)
      })
      .catch(() => {
        if (!gone) {
          setData(null)
          setLoadError('Could not load calendar.')
        }
      })
    return () => {
      gone = true
    }
  }, [brandId, month0, year, monthStart, monthEnd, monthDays, selectedIso, refreshKey])

  const counts = useMemo(() => {
    const next: Record<number, number> = {}
    for (const row of parked) next[row.day] = (next[row.day] || 0) + 1
    return next
  }, [parked])

  const onDay = parked.filter((row) => row.day === selected)
  const selectedMoment = useMemo(
    () =>
      parked.find((r) => r.source === 'moment' && r.calendarId === selectedId)?.item ?? null,
    [parked, selectedId],
  )
  const scheduled = data?.counts?.scheduled ?? 0
  const monthTotal = parked.length
  const highlightToday =
    year === todayYear && month0 === todayMonth0 ? todayDay : undefined

  const reload = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  const handleMove = async (row: Parked) => {
    if (!row.assetId || !moveDate) return
    setActionMsg('')
    try {
      await rescheduleAsset(row.assetId, {
        campaignId: row.campaignId,
        scheduledFor: `${moveDate}T09:00:00`,
        platform: row.platform,
        updatedBy: 'operator',
      })
      setActionMsg(`Moved to ${moveDate}.`)
      setMoveFor(null)
      reload()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Move failed.')
    }
  }

  const handleDuplicate = async (row: Parked) => {
    if (!row.assetId) return
    setActionMsg('')
    try {
      await duplicateScheduledAsset(row.assetId, {
        scheduledFor: row.stamp || `${selectedIso}T09:00:00`,
        campaignId: row.campaignId,
      })
      setActionMsg('Duplicated.')
      reload()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Duplicate failed.')
    }
  }

  const handleUnschedule = async (row: Parked) => {
    if (!row.assetId) return
    setActionMsg('')
    try {
      await unscheduleAsset(row.assetId)
      setActionMsg('Unscheduled.')
      reload()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Unschedule failed.')
    }
  }

  const handleTransition = async (row: Parked, status: string) => {
    if (!row.calendarId || !brandId) return
    setActionMsg('')
    try {
      await transitionCalendarRecord({
        brand_id: brandId,
        calendar_id: row.calendarId,
        new_status: status,
        reason: 'operator',
      })
      setActionMsg('Updated moment.')
      reload()
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Update failed.')
    }
  }

  const emptyCopy = noCalendarConfig
    ? 'This brand has no calendar config yet — moments from marketing calendar will not appear.'
    : loadError
      ? loadError
      : monthTotal === 0
        ? 'Nothing parked this month. Park a draft from Ideas or Studio.'
        : ''

  return (
    <div className="space-y-6">
      <PageIntro icon={CalendarDays} badge="Schedule" here="/calendar" title={monthLabel}>
        Click a day to see what’s parked, or park a draft on an empty one.
      </PageIntro>

      <div className="flex flex-wrap items-center gap-2">
        <Tip text="Previous month">
          <button
            type="button"
            onClick={() => shiftMonth(-1)}
            className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1.5 text-sm font-semibold text-tx hover:border-ac"
          >
            <ChevronLeft className="h-4 w-4" />
            Prev
          </button>
        </Tip>
        <Tip text="Jump to today">
          <button
            type="button"
            onClick={goToday}
            className="rounded-full border border-white/10 px-3 py-1.5 text-sm font-semibold text-yel hover:border-yel"
          >
            Today
          </button>
        </Tip>
        <Tip text="Next month">
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-1.5 text-sm font-semibold text-tx hover:border-ac"
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </button>
        </Tip>
        <ClassicLink href="/?page=calendar" label="calendar" />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          icon={Send}
          label="Today"
          value={data ? scheduled : '—'}
          hint="Scheduled to go live"
          tone="gold"
          stamp={data?.ts}
          stampKind="as_of"
        />
        <StatCard
          to={`/calendar/lanes?date=${selectedIso}`}
          icon={Map}
          label="Lanes"
          value="Open"
          hint="Themes and planning"
          tone="mute"
        />
        <StatCard
          to={`/calendar/ideas?date=${selectedIso}`}
          icon={Lightbulb}
          label="Ideas"
          value="Open"
          hint="Backlog to park"
          tone="mute"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(360px,1fr)]">
        <HeroPanel
          icon={CalendarDays}
          kicker="This month"
          title={
            onDay.length
              ? `${onDay.length} parked on ${selected} ${monthName}`
              : `Nothing parked on ${selected} ${monthName}`
          }
          meta={`${monthTotal} on the month grid. Gold is the day you picked. A green dot means something is already there.`}
          extra={
            <MonthGrid
              embedded
              year={year}
              month0={month0}
              highlight={highlightToday}
              counts={counts}
              selected={selected}
              onSelect={selectDay}
            />
          }
        >
          <Button
            to={toolTo('calendar', { date: selectedIso })}
            icon={CalendarDays}
            tip={`Open the full calendar on ${selected} ${monthName} so you can move and park posts.`}
          >
            Open this day
          </Button>
          <Button
            to={toolTo('ideas', { date: selectedIso })}
            icon={Lightbulb}
            tone="ghost"
            tip={`Open the ideas backlog and drop one onto ${selected} ${monthName}.`}
          >
            Park an idea
          </Button>
        </HeroPanel>
        <section
          className={
            selectedMoment
              ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(360px,1fr)]'
              : undefined
          }
        >
          <div>
          <h2 className="mb-3 font-display text-xl font-semibold">
            {selected === highlightToday && highlightToday != null ? 'Today' : `${selected} ${monthName}`}
          </h2>
          {actionMsg ? <p className="mb-2 text-sm text-ac">{actionMsg}</p> : null}
          <ul className="space-y-2">
            {onDay.map((row) => {
              const rowFooter = (
                <>
                  {row.assetId && ['campaign', 'calendar', 'queue', 'slot'].includes(row.source || '') ? (
                    <div className="flex flex-wrap gap-2 text-xs">
                      <button
                        type="button"
                        className="text-ac hover:text-yel"
                        onClick={() => {
                          setMoveFor(row.key)
                          setMoveDate(selectedIso)
                        }}
                      >
                        Move to…
                      </button>
                      <button type="button" className="text-ac hover:text-yel" onClick={() => handleDuplicate(row)}>
                        Duplicate
                      </button>
                      <button type="button" className="text-ac hover:text-yel" onClick={() => handleUnschedule(row)}>
                        Unschedule
                      </button>
                    </div>
                  ) : null}
                  {row.calendarId && row.source === 'moment' ? (
                    <div className="flex flex-wrap gap-2 text-xs">
                      <button
                        type="button"
                        className="text-ac hover:text-yel"
                        onClick={() => handleTransition(row, 'ignored')}
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : null}
                  {moveFor === row.key ? (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <input
                        type="date"
                        value={moveDate}
                        onChange={(e) => setMoveDate(e.target.value)}
                        className="rounded-lg border border-white/10 bg-bg2 px-2 py-1 text-sm"
                      />
                      <button
                        type="button"
                        className="rounded-full bg-yel px-3 py-1 text-xs font-semibold text-bg"
                        onClick={() => handleMove(row)}
                      >
                        Save
                      </button>
                      <button type="button" className="text-xs text-tx3" onClick={() => setMoveFor(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : null}
                </>
              )
              return (
                <QueueItem
                  key={row.key}
                  to={row.to}
                  badge={row.badge}
                  tone="green"
                  title={row.title}
                  meta={row.meta}
                  stamp={row.stamp}
                  stampKind={row.stampKind}
                  dateOnly={row.source === 'moment'}
                  tip={
                    row.source === 'moment'
                      ? 'Open this calendar moment — why, angles, and source.'
                      : 'Open this parked piece.'
                  }
                  action={
                    row.color ? (
                      <span
                        className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: row.color }}
                        aria-hidden
                      />
                    ) : undefined
                  }
                  footer={rowFooter}
                />
              )
            })}
            {data && onDay.length === 0 && emptyCopy ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                {emptyCopy}
              </li>
            ) : null}
            {data && onDay.length === 0 && !emptyCopy ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Nothing on {selected} {monthName}. Park a draft from Ideas or Studio.
              </li>
            ) : null}
          </ul>
          <div className="mt-4 grid gap-2">
            <IconTile href="/calendar/lanes" icon={Map} label="Planning" hint="Themes and lanes" />
            <IconTile href="/calendar/ideas" icon={Lightbulb} label="Ideas" hint="Backlog to schedule" />
          </div>
          </div>
          {selectedMoment ? (
            <MomentPanel
              item={selectedMoment}
              onClose={closeMoment}
              onDismiss={() => {
                const row = parked.find(
                  (r) => r.source === 'moment' && r.calendarId === selectedId,
                )
                if (row) handleTransition(row, 'ignored')
                closeMoment()
              }}
            />
          ) : null}
        </section>
      </div>
    </div>
  )
}
