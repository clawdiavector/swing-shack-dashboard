import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FILTER_QUERY, withQueryParam } from '../../../lib/backNav'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { planPageHref } from '../../../lib/calendarAlerts'
import {
  buildMonthGridCells,
  filterMonthItemsByLane,
  findFeaturedDate,
  LANE_META,
  LANE_FILTER_ORDER,
  laneLabel,
  localTodayIso,
  monthSummaryStats,
  monthlyThemeLabel,
  shiftMonthParam,
  truncateChipTitle,
} from '../../../lib/planning'
import type { PlanningMonthItem, PlanningMonthView } from '../../../lib/planningTypes'
import { EventTypeIcon } from '../../../components/EventTypeIcon'
import {
  groupByDay,
  readShowPlanSteps,
  readShowSuggestions,
  saveShowPlanSteps,
  saveShowSuggestions,
} from '../../../lib/calendarSuggestions'
import { stepsByDay } from '../../../lib/planSteps'
import { PlanStepChip, useMonthPlanSteps } from './PlanStepChips'
import { DayPostSuggestions } from './DayPostSuggestions'
import { SuggestionBar, useMonthSuggestions } from './MonthSuggestions'

const DOW = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

const OUTSIDE_GREY = '#9ca3af'

function isOutsideCampaignItem(it: PlanningMonthItem): boolean {
  return (
    it.post_type === 'posted-outside-campaign-os' ||
    it.execution_type === 'outside_campaign_os'
  )
}

function OutsidePostChip({ item }: { item: PlanningMonthItem }) {
  const label = item.outside_label || 'Posted outside Campaign OS'
  const title = truncateChipTitle(item.title || label)
  return (
    <span
      className="inline-flex max-w-full items-center gap-1 truncate rounded-full border px-2 py-0.5 text-[10.5px] font-semibold"
      style={{
        background: `${OUTSIDE_GREY}22`,
        color: OUTSIDE_GREY,
        borderColor: `${OUTSIDE_GREY}66`,
      }}
      title={label}
    >
      {item.thumbnail_url ? (
        <img
          src={item.thumbnail_url}
          alt=""
          className="h-4 w-4 shrink-0 rounded-full object-cover"
        />
      ) : (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: OUTSIDE_GREY }} />
      )}
      {title}
    </span>
  )
}

function LaneChip({
  lane,
  title,
  status,
  kind,
}: {
  lane?: string
  title?: string
  status?: string
  kind?: string
}) {
  const meta = LANE_META[lane || ''] || { color: 'var(--color-tx3)', label: lane || '—' }
  const opacity = status === 'NEEDS_CAPTURE' ? 0.55 : 1
  return (
    <span
      className="inline-flex max-w-full items-center gap-1 truncate rounded-full border px-2 py-0.5 text-[10.5px] font-semibold"
      style={{
        background: `${meta.color}22`,
        color: meta.color,
        borderColor: `${meta.color}55`,
        opacity,
      }}
      title={`${title || ''} — ${lane} (${status || ''})`}
    >
      {kind ? (
        <EventTypeIcon kind={kind} size="sm" className="!border-0 !bg-transparent !p-0" />
      ) : (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: meta.color }} />
      )}
      {truncateChipTitle(title || '')}
    </span>
  )
}

function DayDrawer({
  brand,
  iso,
  items,
  onClose,
}: {
  brand: string
  iso: string | null
  items: PlanningMonthItem[]
  onClose: () => void
}) {
  if (!iso) return null
  const dateObj = new Date(`${iso}T00:00:00`)
  const dayName = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][
    dateObj.getDay() === 0 ? 6 : dateObj.getDay() - 1
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Day detail ${iso}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-bd bg-bg2 p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold tracking-wider text-tx3 uppercase">{dayName}</p>
            <p className="font-display text-2xl font-extrabold">{iso}</p>
            <p className="text-xs text-tx3">
              {items.length} item{items.length === 1 ? '' : 's'} planned
            </p>
          </div>
          <button type="button" className="text-2xl text-tx2 hover:text-tx" onClick={onClose}>
            ×
          </button>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-tx3">Nothing scheduled for this day. A clear one!</p>
        ) : (
          <ul className="space-y-4">
            {items.map((it, i) => {
              const outside = isOutsideCampaignItem(it)
              const statusColor =
                it.status === 'READY'
                  ? '#10b981'
                  : it.status === 'NEEDS_CAPTURE'
                    ? '#f97316'
                    : '#6b7280'
              return (
                <li key={`${it.title}-${i}`} className="space-y-2 border-b border-bd/50 pb-4 last:border-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {outside ? (
                      <OutsidePostChip item={it} />
                    ) : (
                      <LaneChip lane={it.lane} title={laneLabel(it.lane, brand)} status={it.status} kind={it.kind} />
                    )}
                    {it.status ? (
                      <span
                        className="rounded-full border px-2 py-0.5 text-[10px]"
                        style={{
                          background: `${statusColor}22`,
                          color: statusColor,
                          borderColor: `${statusColor}55`,
                        }}
                      >
                        {it.status}
                      </span>
                    ) : null}
                    {it.is_paid_supported ? (
                      <span className="rounded-full border border-purple-500/40 bg-purple-500/15 px-2 py-0.5 text-[10px] text-purple-400">
                        paid
                      </span>
                    ) : null}
                  </div>
                  <p className="font-semibold">{it.title || it.hook || '—'}</p>
                  {outside && it.outside_label ? (
                    <p className="text-xs font-semibold text-tx3">{it.outside_label}</p>
                  ) : null}
                  {outside && it.thumbnail_url ? (
                    <img
                      src={it.thumbnail_url}
                      alt=""
                      className="max-h-32 rounded-lg border border-bd object-cover"
                    />
                  ) : null}
                  {outside && it.permalink ? (
                    <a
                      href={it.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex text-xs font-semibold text-yel hover:underline"
                    >
                      Open post
                    </a>
                  ) : null}
                  {it.subtitle ? <p className="text-sm text-tx2">{it.subtitle}</p> : null}
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-tx2">
                    <dt className="text-tx3">Pillar</dt>
                    <dd>{!it.lane || it.lane === 'operator' ? 'Not set' : it.lane}</dd>
                    {it.channel ? (
                      <>
                        <dt className="text-tx3">Channel</dt>
                        <dd>{it.channel}</dd>
                      </>
                    ) : null}
                    {it.cta ? (
                      <>
                        <dt className="text-tx3">CTA</dt>
                        <dd className="font-semibold">{it.cta}</dd>
                      </>
                    ) : null}
                    {it.purpose ? (
                      <>
                        <dt className="text-tx3">Purpose</dt>
                        <dd>{it.purpose}</dd>
                      </>
                    ) : null}
                    {it.property ? (
                      <>
                        <dt className="text-tx3">Property</dt>
                        <dd>{it.property}</dd>
                      </>
                    ) : null}
                    {it.stock_refs?.length ? (
                      <>
                        <dt className="text-tx3">Stock</dt>
                        <dd>{it.stock_refs.join(', ')}</dd>
                      </>
                    ) : null}
                  </dl>
                  {it.event_key || it.title ? (
                    <Link
                      to={planPageHref({ event_key: it.event_key, name: it.title })}
                      className="inline-flex rounded-full border border-yel/40 bg-yel/15 px-3 py-1 text-xs font-semibold text-yel hover:bg-yel/25"
                    >
                      Open in the list
                    </Link>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

export function LaneMonthPanel({
  brand,
  monthParam,
  monthView,
  onMonthChange,
  onSuggestDate,
  brandId = '',
  onChanged,
}: {
  brand: string
  monthParam: string
  monthView: PlanningMonthView | null
  onMonthChange: (next: string) => void
  onSuggestDate?: (iso: string) => void
  /** The brand's id; suggestions are drawn only when one brand is chosen. */
  brandId?: string
  /** Called after a suggestion is approved, rejected or undone, to reload the month. */
  onChanged?: () => void
}) {
  const [params, setParams] = useSearchParams()
  const laneFilter = params.get(FILTER_QUERY) || ''
  function setLaneFilter(next: string) {
    setParams((prev) => withQueryParam(prev, FILTER_QUERY, next || null), { replace: true })
  }
  const [drawerIso, setDrawerIso] = useState<string | null>(null)
  const [showGhosts, setShowGhosts] = useState(readShowSuggestions)
  const noop = useCallback(() => {}, [])
  const sug = useMonthSuggestions(brandId, monthParam, showGhosts && Boolean(brandId), onChanged || noop)
  const ghostsByDay = useMemo(() => groupByDay(sug.items), [sug.items])
  const [showPlanSteps, setShowPlanSteps] = useState(readShowPlanSteps)
  const planSteps = useMonthPlanSteps(brandId, monthParam, showPlanSteps)
  const planStepsByDay = useMemo(() => stepsByDay(planSteps), [planSteps])

  const [year, month1] = monthParam.split('-').map(Number)
  const todayIso = localTodayIso()
  const monthNames = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ]

  const cells = useMemo(
    () => buildMonthGridCells(year, month1, todayIso),
    [year, month1, todayIso],
  )

  const featuredDate = useMemo(
    () => findFeaturedDate(monthView?.days, monthParam),
    [monthView?.days, monthParam],
  )

  const stats = useMemo(
    () => monthSummaryStats(monthView?.days, monthParam),
    [monthView?.days, monthParam],
  )

  const themeLabel = useMemo(
    () => monthlyThemeLabel(monthView?.monthly_theme),
    [monthView?.monthly_theme],
  )

  const drawerItems = drawerIso ? monthView?.days?.[drawerIso] || [] : []

  const closeDrawer = useCallback(() => setDrawerIso(null), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDrawer()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [closeDrawer])

  const seenMonth = useRef<string | null>(null)
  useEffect(() => {
    if (seenMonth.current === null) {
      seenMonth.current = monthParam
      return
    }
    if (seenMonth.current === monthParam) return
    seenMonth.current = monthParam
    setParams((prevParams) => withQueryParam(prevParams, FILTER_QUERY, null), { replace: true })
  }, [monthParam, setParams])

  if (!monthView?.ok) {
    return (
      <section className="glass rounded-2xl border border-white/10 p-4">
        <p className="text-sm text-tx3">No month plan for {brand} in {monthParam}.</p>
      </section>
    )
  }

  return (
    <section className="glass space-y-4 rounded-2xl border border-white/10 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold">
          {monthNames[month1 - 1]} {year} — calendar grid
        </h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-lg border border-bd px-2 py-1 text-sm hover:border-yel"
            aria-label="Previous month"
            onClick={() => onMonthChange(shiftMonthParam(monthParam, -1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <input
            type="month"
            value={monthParam}
            onChange={(e) => onMonthChange(e.target.value)}
            className="rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx"
          />
          <button
            type="button"
            className="rounded-lg border border-bd px-2 py-1 text-sm hover:border-yel"
            aria-label="Next month"
            onClick={() => onMonthChange(shiftMonthParam(monthParam, 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {themeLabel ? (
        <p className="text-sm font-semibold text-yel">{themeLabel}</p>
      ) : null}

      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setLaneFilter('')}
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10.5px] font-semibold ${
            !laneFilter ? 'outline-2 outline-offset-2 outline-yel' : 'border-bd bg-bg2'
          }`}
        >
          All lanes
        </button>
        {LANE_FILTER_ORDER.map((l) => {
          const m = LANE_META[l]
          return (
            <button
              key={l}
              type="button"
              onClick={() => setLaneFilter(l)}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10.5px] font-semibold ${
                laneFilter === l ? 'outline-2 outline-offset-2' : ''
              }`}
              style={{
                background: `${m.color}18`,
                color: m.color,
                borderColor: `${m.color}55`,
                outlineColor: m.color,
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.color }} />
              {laneLabel(l, brand)}
            </button>
          )
        })}
      </div>
      {brandId ? (
        <SuggestionBar
          show={showGhosts}
          onToggle={(v) => {
            setShowGhosts(v)
            saveShowSuggestions(v)
          }}
          count={sug.items.length}
          showPlans={showPlanSteps}
          onTogglePlans={(v) => {
            setShowPlanSteps(v)
            saveShowPlanSteps(v)
          }}
          planStepCount={planSteps.length}
          decided={sug.decided}
          busy={sug.busyKey !== null}
          error={sug.error}
          onUndo={sug.undo}
          onDismiss={sug.dismiss}
          onMakePlan={sug.makePlan}
          planBusy={sug.planBusy}
          planNote={sug.planNote}
        />
      ) : null}
      <p className="text-xs text-tx3">
        {laneFilter
          ? `Filtering by ${laneLabel(laneFilter, brand)}. Click a day to see all lanes.`
          : 'Showing all lanes. Click a lane chip to filter.'}
      </p>

      <div className="grid grid-cols-[repeat(7,minmax(0,1fr))] gap-1.5">
        {DOW.map((d, i) => (
          <div
            key={d}
            className={`py-1 text-center text-[10px] font-bold tracking-wider text-tx3 uppercase ${
              i >= 5 ? 'text-tx3/80' : ''
            }`}
          >
            {d}
          </div>
        ))}
        {cells.map((cell) => {
          const allItems = monthView.days?.[cell.iso] || []
          const items = filterMonthItemsByLane(allItems, laneFilter)
          const ghosts = showGhosts ? ghostsByDay[cell.iso] || [] : []
          const dayPrimary = sug.postsByDay[cell.iso] || []
          const steps = planStepsByDay[cell.iso] || []
          const isFeatured = cell.iso === featuredDate
          return (
            <button
              key={cell.iso}
              type="button"
              onClick={() => setDrawerIso(cell.iso)}
              className={`min-h-[88px] rounded-lg border p-1.5 text-left transition-colors hover:border-yel/40 ${
                cell.isToday ? 'border-yel/60 bg-yel/5' : 'border-bd/60 bg-bg2/50'
              } ${cell.isWeekend ? 'bg-bg3/40' : ''} ${!cell.inMonth ? 'opacity-45' : ''} ${
                isFeatured ? 'ring-1 ring-yel/30' : ''
              }`}
            >
              <div className="mb-1 flex items-baseline justify-between gap-1">
                <span className={`text-xs font-bold ${cell.isToday ? 'text-yel' : 'text-tx'}`}>
                  {cell.dayNum}
                </span>
                <div className="flex items-center gap-1">
                  {allItems.length > 0 ? (
                    <span className="text-[9px] text-tx3">
                      {allItems.length} {allItems.length === 1 ? 'lane' : 'lanes'}
                    </span>
                  ) : null}
                  {/* V2.11 — single-click add affordance. The day cell
                      still opens the drawer on click; this is a
                      separate "+ add" pip that fires SuggestDate. */}
                  {onSuggestDate && cell.inMonth ? (
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => {
                        e.stopPropagation()
                        onSuggestDate(cell.iso)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.stopPropagation()
                          onSuggestDate(cell.iso)
                        }
                      }}
                      className="inline-flex h-4 min-w-4 cursor-pointer items-center justify-center rounded-full bg-yel/20 px-1 text-[9px] font-bold text-yel hover:bg-yel/30"
                      data-testid="month-day-add"
                      title="Add to Main Calendar"
                    >
                      +
                    </span>
                  ) : null}
                </div>
              </div>
              {items.length === 0 &&
              ghosts.length === 0 &&
              dayPrimary.length === 0 &&
              steps.length === 0 &&
              cell.inMonth ? (
                <span className="text-[9px] text-tx3 italic">no content</span>
              ) : (
                <div className="flex flex-col gap-0.5">
                  {items.map((it, idx) =>
                    isOutsideCampaignItem(it) ? (
                      <OutsidePostChip key={`outside-${it.title}-${idx}`} item={it} />
                    ) : (
                      <LaneChip key={`${it.title}-${idx}`} lane={it.lane} title={it.title} status={it.status} kind={it.kind} />
                    ),
                  )}
                  {steps.map((st) => (
                    <PlanStepChip key={st.key} s={st} brandId={brandId} />
                  ))}
                  {brandId ? (
                    <DayPostSuggestions
                      iso={cell.iso}
                      postsByDay={sug.postsByDay}
                      ghosts={ghosts}
                      busyKey={sug.busyKey}
                      pillars={sug.pillars}
                      onApprove={(g, pillar) => void sug.approve(g, pillar)}
                      onReject={(g) => void sug.reject(g)}
                      onSwap={(g) => void sug.swap(g)}
                    />
                  ) : null}
                </div>
              )}
            </button>
          )
        })}
      </div>

      <div className="text-[11px] text-tx3 italic">
        <p>
          Featured day: <b className="text-tx">{featuredDate || '—'}</b> with the highest lane
          density. Click any day to see all items.
        </p>
        <p className="mt-2 not-italic">
          {stats.totalItems} items across {stats.activeDays} active days in this month.
        </p>
      </div>

      <DayDrawer brand={brand} iso={drawerIso} items={drawerItems} onClose={closeDrawer} />
    </section>
  )
}
