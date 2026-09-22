import { CalendarDays, ChevronLeft, ChevronRight, Lightbulb, Map, Send } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, MonthGrid, PageIntro } from '../components/chrome'
import { Button, ClassicLink, IconTile, QueueItem, StatCard, Tip } from '../components/ui'
import {
  duplicateScheduledAsset,
  fetchCalendarMonth,
  fetchIntelCalendar,
  fetchToday,
  rescheduleAsset,
  transitionCalendarRecord,
  unscheduleAsset,
  type TodayPanel,
} from '../lib/api'
import { dayInMonth, isoDate, parseIsoDateParam } from '../lib/stamp'
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
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

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
              return {
                key: `cal:${item.calendar_id || item.title}`,
                day,
                title: item.title || 'Untitled',
                badge: item.type || item.status || 'moment',
                to: toolTo('calendar', { id: item.calendar_id, date }),
                stamp: item.event_date || item.campaign_start,
                stampKind: 'scheduled',
                source: 'moment',
                calendarId: item.calendar_id,
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
          href="/?page=planning"
          icon={Map}
          label="Lanes"
          value="Open"
          hint="Themes and planning"
          tone="mute"
        />
        <StatCard
          href="/?page=ideas"
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
        <section>
          <h2 className="mb-3 font-display text-xl font-semibold">
            {selected === highlightToday && highlightToday != null ? 'Today' : `${selected} ${monthName}`}
          </h2>
          {actionMsg ? <p className="mb-2 text-sm text-ac">{actionMsg}</p> : null}
          <ul className="space-y-2">
            {onDay.map((row) => (
              <li key={row.key}>
                <QueueItem
                  to={row.to}
                  badge={row.badge}
                  tone="green"
                  title={row.title}
                  stamp={row.stamp}
                  stampKind={row.stampKind}
                  tip="Open this parked piece."
                />
                {row.color ? (
                  <span
                    className="ml-2 inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: row.color }}
                    aria-hidden
                  />
                ) : null}
                {row.assetId && ['campaign', 'calendar', 'queue', 'slot'].includes(row.source || '') ? (
                  <div className="mt-1 flex flex-wrap gap-2 text-xs">
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
                  <div className="mt-1 flex flex-wrap gap-2 text-xs">
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
              </li>
            ))}
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
            <IconTile href="/?page=planning" icon={Map} label="Planning" hint="Themes and lanes" />
            <IconTile href="/?page=ideas" icon={Lightbulb} label="Ideas" hint="Backlog to schedule" />
          </div>
        </section>
      </div>
    </div>
  )
}
