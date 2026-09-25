import { CalendarDays, ChevronDown } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { PostCard } from '../components/posting/PostCard'
import { Badge } from '../components/ui'
import { fetchPostingWeek } from '../lib/api'
import { formatPostingDayHeader, type PostingWeekDay } from '../lib/postingWeek'

function DaySection({ day }: { day: PostingWeekDay }) {
  return (
    <section key={day.date}>
      <div className="mb-2 flex items-center gap-2">
        <CalendarDays className="h-4 w-4 text-ac" strokeWidth={2} />
        <h2 className="font-display text-lg font-semibold">
          {formatPostingDayHeader(day)}
          {day.is_today ? (
            <span className="ml-2 text-xs font-semibold uppercase text-yel">Today</span>
          ) : null}
        </h2>
        <Badge tone="mute">{day.posts.length}</Badge>
      </div>
      {day.posts.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
          Nothing going out.
        </p>
      ) : (
        <ul className="space-y-2">
          {day.posts.map((post) => (
            <PostCard key={post.calendar_id} post={post} dayDate={day.date} weekday={day.weekday} />
          ))}
        </ul>
      )}
    </section>
  )
}

export function WeekBoard() {
  const { brandId: activeBrand } = useBrand()
  const brandId = activeBrand ?? 'swing-shack'
  const [days, setDays] = useState<PostingWeekDay[]>([])
  const [undated, setUndated] = useState<PostingWeekDay['posts']>([])
  const [undatedTotal, setUndatedTotal] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchPostingWeek(brandId, { past: 3, days: 7 })
      .then((payload) => {
        if (!payload.ok) {
          setError(payload.error || 'Failed to load week board')
          return
        }
        setDays(payload.days_list || [])
        setUndated(payload.undated || [])
        setUndatedTotal(payload.undated_total ?? payload.undated?.length ?? 0)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
  }, [brandId])

  const { pastDays, futureDays } = useMemo(() => {
    const past = days.filter((d) => d.is_past)
    const future = days.filter((d) => !d.is_past)
    return { pastDays: past, futureDays: future }
  }, [days])

  const pastCount = pastDays.reduce((n, d) => n + d.posts.length, 0)

  if (error) {
    return (
      <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
    )
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/week" title="This week">
        Every post for this brand — past three days, today through the next six, and undated backlog.
      </PageIntro>

      {pastDays.length > 0 ? (
        <details className="group rounded-2xl border border-bd bg-bg-2/30 px-4 py-3">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-display text-base font-semibold">
            <span className="flex items-center gap-2">
              <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
              Past 3 days
            </span>
            <Badge tone="mute">{pastCount}</Badge>
          </summary>
          <div className="mt-4 space-y-5">
            {pastDays.map((day) => (
              <DaySection key={day.date} day={day} />
            ))}
          </div>
        </details>
      ) : null}

      <div className="space-y-5">
        {futureDays.map((day) => (
          <DaySection key={day.date} day={day} />
        ))}
      </div>

      {undated.length > 0 || undatedTotal > 0 ? (
        <section>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Undated</h2>
            <Badge tone="gold">
              {undated.length}
              {undatedTotal > undated.length ? ` of ${undatedTotal}` : ''}
            </Badge>
          </div>
          {undatedTotal > undated.length ? (
            <p className="mb-3 text-sm text-tx3">
              Showing {undated.length} of {undatedTotal} undated posts — open Calendar to date the rest.
            </p>
          ) : null}
          <ul className="space-y-2">
            {undated.map((post) => (
              <PostCard
                key={post.calendar_id}
                post={post}
                dayDate=""
                weekday=""
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
