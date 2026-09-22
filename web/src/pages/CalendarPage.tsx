import { CalendarDays, Lightbulb, Map, Send } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, MonthGrid, PageIntro } from '../components/chrome'
import { Button, IconTile, QueueItem, StatCard } from '../components/ui'
import { fetchCalendarMonth, fetchToday, type TodayPanel } from '../lib/api'
import { dayInMonth, isoDate } from '../lib/stamp'
import { toolTo } from '../lib/tools'

type Parked = {
  key: string
  day: number
  title: string
  badge: string
  to: string
  stamp?: string
  stampKind?: string
}

export function CalendarPage() {
  const { brandId } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [parked, setParked] = useState<Parked[]>([])
  const now = new Date()
  const year = now.getFullYear()
  const month0 = now.getMonth()
  const today = now.getDate()
  const [selected, setSelected] = useState(today)
  const month = new Intl.DateTimeFormat('en-ZA', { month: 'long', year: 'numeric' }).format(now)
  const monthName = new Intl.DateTimeFormat('en-ZA', { month: 'long' }).format(now)
  const selectedIso = isoDate(new Date(year, month0, selected))

  useEffect(() => {
    let gone = false
    fetchToday(brandId)
      .then(async (panel) => {
        if (gone) return
        setData(panel)
        const brand = panel.active_brand_id
        const start = isoDate(new Date(year, month0, 1))
        const end = isoDate(new Date(year, month0 + 1, 0))
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
            } satisfies Parked
          })
          .filter((row): row is Parked => Boolean(row))

        if (!brand) {
          setParked(fromCards)
          return
        }
        const view = await fetchCalendarMonth(brand, start, end)
        if (gone) return
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
            } satisfies Parked
          })
          .filter((row): row is Parked => Boolean(row))
        const seen = new Set<string>()
        const merged: Parked[] = []
        for (const row of [...fromCal, ...fromCards]) {
          if (seen.has(row.key)) continue
          seen.add(row.key)
          merged.push(row)
        }
        setParked(merged)
      })
      .catch(() => {
        if (!gone) setData(null)
      })
    return () => {
      gone = true
    }
  }, [brandId, month0, year])

  const counts = useMemo(() => {
    const next: Record<number, number> = {}
    for (const row of parked) next[row.day] = (next[row.day] || 0) + 1
    return next
  }, [parked])

  const onDay = parked.filter((row) => row.day === selected)
  const scheduled = data?.counts?.scheduled ?? 0
  const monthTotal = parked.length

  return (
    <div className="space-y-6">
      <PageIntro icon={CalendarDays} badge="Schedule" here="/calendar" title={month}>
        Click a day to see what’s parked, or park a draft on an empty one.
      </PageIntro>

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
              highlight={today}
              counts={counts}
              selected={selected}
              onSelect={setSelected}
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
            {selected === today ? 'Today' : `${selected} ${monthName}`}
          </h2>
          <ul className="space-y-2">
            {onDay.map((row) => (
              <QueueItem
                key={row.key}
                to={row.to}
                badge={row.badge}
                tone="green"
                title={row.title}
                stamp={row.stamp}
                stampKind={row.stampKind}
                tip="Open this parked piece."
              />
            ))}
            {data && onDay.length === 0 ? (
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
