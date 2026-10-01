import { CalendarDays, ChevronDown } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrandScope } from '../components/BrandSwitch'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
import { PageIntro } from '../components/chrome'
import { PostCard } from '../components/posting/PostCard'
import { Badge } from '../components/ui'
import {
  enqueueOneshotDay,
  fetchBrandImagesToday,
  fetchPostingWeek,
  fetchTemplateGallery,
  scheduleDay,
} from '../lib/api'
import type { BrandImagesToday } from '../lib/api'
import { fanOutPayloads, mergePostingWeekPayloads, type FanOutFailure } from '../lib/fanOut'
import { useLoadGate } from '../lib/useLoadGate'
import {
  dayAnchorFromParams,
  formatPostingDayHeader,
  renderModeOf,
  sastTodayIso,
  sastTomorrowIso,
  type PostingWeekDay,
  type PostingWeekPost,
} from '../lib/postingWeek'

function unionPostTypeHints(templates: { post_type_hints?: string[] }[]): string[] {
  const set = new Set<string>()
  for (const t of templates) {
    for (const h of t.post_type_hints ?? []) {
      const v = String(h).trim().toLowerCase()
      if (v) set.add(v)
    }
  }
  return [...set].sort()
}

const SCHEDULE_BRAND_LABEL: Record<string, string> = {
  'swing-shack': 'Swing Shack',
  stick: 'Stick',
}

function DaySection({
  day,
  waitForReads,
  editable,
  postTypeByBrand,
  onRefresh,
  scheduleBrandIds,
  onSchedule,
  scheduling,
  scheduleMessage,
}: {
  day: PostingWeekDay
  waitForReads?: () => Promise<void>
  editable?: boolean
  postTypeByBrand?: Record<string, string[]>
  onRefresh?: () => void
  scheduleBrandIds?: string[]
  onSchedule?: (dateIso: string) => void
  scheduling?: boolean
  scheduleMessage?: string
}) {
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
        <div className="space-y-3 rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
          <p>Nothing going out.</p>
          {editable && scheduleBrandIds?.length ? (
            <>
              <p className="text-xs">Adds candidate cards — nothing generates.</p>
              <button
                type="button"
                disabled={scheduling}
                className="rounded-full bg-ac px-4 py-2 text-xs font-semibold text-bg disabled:opacity-40"
                onClick={() => onSchedule?.(day.date)}
              >
                Schedule this day
              </button>
              {scheduleMessage ? <p className="text-xs text-tx2">{scheduleMessage}</p> : null}
            </>
          ) : null}
        </div>
      ) : (
        <ul className="space-y-2">
          {day.posts.map((post) => (
            <PostCard
              key={`${post.brand_id ?? ''}:${post.calendar_id}`}
              post={post}
              dayDate={day.date}
              weekday={day.weekday}
              waitForReads={waitForReads}
              editable={editable}
              postTypeOptions={postTypeByBrand?.[post.brand_id ?? ''] ?? []}
              onRefresh={onRefresh}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

export function WeekBoard() {
  const { isAll, brandIds, scope } = useBrandScope()
  const { trackLoad, waitForLoad } = useLoadGate()
  const [params, setParams] = useSearchParams()
  const tabParam = params.get('tab')
  const dateParam = params.get('date')
  const { tab, dateIso } = dayAnchorFromParams(tabParam, dateParam)
  const isDayMode = tab === 'day'

  const [days, setDays] = useState<PostingWeekDay[]>([])
  const [undated, setUndated] = useState<PostingWeekDay['posts']>([])
  const [undatedTotal, setUndatedTotal] = useState(0)
  const [error, setError] = useState('')
  const [failures, setFailures] = useState<FanOutFailure[]>([])
  const [postTypeByBrand, setPostTypeByBrand] = useState<Record<string, string[]>>({})
  const [capInfo, setCapInfo] = useState<BrandImagesToday | null>(null)
  const [oneshotMsg, setOneshotMsg] = useState('')
  const [oneshotBusy, setOneshotBusy] = useState(false)
  const [scheduling, setScheduling] = useState(false)
  const [scheduleMessage, setScheduleMessage] = useState('')

  const singleBrandId = scope === 'all' ? 'swing-shack' : scope
  const scheduleBrandIds = isAll ? brandIds : [singleBrandId]

  const dayPosts: PostingWeekPost[] = useMemo(() => {
    if (!isDayMode || days.length === 0) return []
    return days[0]?.posts ?? []
  }, [days, isDayMode])

  const hasOneshotCard = useMemo(
    () => dayPosts.some((p) => renderModeOf(p) === 'oneshot'),
    [dayPosts],
  )

  const weekFetchOpts = useMemo(
    () =>
      isDayMode
        ? { start: dateIso, days: 1, past: 0, includeUndated: false as const }
        : { past: 3, days: 7 },
    [isDayMode, dateIso],
  )

  const load = useCallback(() => {
    const run = async (): Promise<void> => {
      setFailures([])
      if (isAll) {
        const { payloads, failures: fails } = await fanOutPayloads(brandIds, (brandId) =>
          fetchPostingWeek(brandId, weekFetchOpts),
        )
        setFailures(fails)
        const merged = mergePostingWeekPayloads(payloads, brandIds)
        if (!merged.ok) {
          setError(merged.error || 'Failed to load week board')
          return
        }
        setDays(merged.days_list || [])
        setUndated(isDayMode ? [] : merged.undated || [])
        setUndatedTotal(isDayMode ? 0 : merged.undated_total ?? merged.undated?.length ?? 0)
        setError('')
        return
      }
      fetchPostingWeek(singleBrandId, weekFetchOpts)
        .then((payload) => {
          if (!payload.ok) {
            setError(payload.error || 'Failed to load week board')
            return
          }
          setDays(payload.days_list || [])
          setUndated(isDayMode ? [] : payload.undated || [])
          setUndatedTotal(isDayMode ? 0 : payload.undated_total ?? payload.undated?.length ?? 0)
          setError('')
        })
        .catch((err: Error) => setError(err.message))
    }
    trackLoad(run())
  }, [isAll, brandIds, singleBrandId, trackLoad, weekFetchOpts, isDayMode])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!isDayMode) {
      setCapInfo(null)
      return
    }
    let cancelled = false
    void fetchBrandImagesToday(singleBrandId)
      .then((payload) => {
        if (!cancelled) setCapInfo(payload)
      })
      .catch(() => {
        if (!cancelled) setCapInfo(null)
      })
    return () => {
      cancelled = true
    }
  }, [isDayMode, singleBrandId, dateIso])

  useEffect(() => {
    if (!isDayMode) return
    const brands = isAll ? brandIds : [singleBrandId]
    let cancelled = false
    void (async () => {
      const next: Record<string, string[]> = {}
      await Promise.all(
        brands.map(async (brandId) => {
          try {
            const gallery = await fetchTemplateGallery(brandId)
            const templates = gallery.templates ?? gallery.sections?.flatMap((s) => s.templates) ?? []
            next[brandId] = unionPostTypeHints(templates)
          } catch {
            next[brandId] = []
          }
        }),
      )
      if (!cancelled) setPostTypeByBrand(next)
    })()
    return () => {
      cancelled = true
    }
  }, [isDayMode, isAll, brandIds, singleBrandId])

  const setDeskParams = (nextTab: 'week' | 'day', nextDate: string) => {
    const q = new URLSearchParams(params)
    if (nextTab === 'week') {
      q.delete('tab')
      q.delete('date')
    } else {
      q.set('tab', 'day')
      q.set('date', nextDate)
    }
    setParams(q, { replace: true })
  }

  const { pastDays, futureDays } = useMemo(() => {
    const past = days.filter((d) => d.is_past)
    const future = days.filter((d) => !d.is_past)
    return { pastDays: past, futureDays: future }
  }, [days])

  const pastCount = pastDays.reduce((n, d) => n + d.posts.length, 0)

  const daySections = isDayMode ? days : futureDays

  const oneshotDisabled =
    !isDayMode ||
    !hasOneshotCard ||
    Boolean(capInfo?.at_cap) ||
    Boolean(capInfo?.at_oneshot_cap)
  const oneshotTitle = !hasOneshotCard
    ? 'No one-shot cards on this day'
    : capInfo?.at_oneshot_cap
      ? 'One-shot cap reached for this brand today'
      : capInfo?.at_cap
        ? 'Daily image cap reached'
        : 'Generate one-shots for this day'

  async function generateOneshots() {
    if (oneshotDisabled || oneshotBusy) return
    setOneshotBusy(true)
    setOneshotMsg('')
    try {
      const res = await enqueueOneshotDay({
        brand_id: singleBrandId,
        date: dateIso,
        editor: 'week-board',
      })
      const enq = res.enqueued?.length ?? 0
      const skip = res.skipped?.length ?? 0
      setOneshotMsg(`Enqueued ${enq}, skipped ${skip}`)
      load()
      const cap = await fetchBrandImagesToday(singleBrandId)
      setCapInfo(cap)
    } catch (err) {
      setOneshotMsg(err instanceof Error ? err.message : 'Generate failed')
    } finally {
      setOneshotBusy(false)
    }
  }

  const handleScheduleDay = useCallback(
    async (dayIso: string) => {
      setScheduling(true)
      setScheduleMessage('')
      const parts: string[] = []
      try {
        for (const brandId of scheduleBrandIds) {
          const label = SCHEDULE_BRAND_LABEL[brandId] ?? brandId
          const result = await scheduleDay(brandId, dayIso)
          if (result.ok) {
            const n = (result.counts?.template ?? 0) + (result.counts?.oneshot ?? 0)
            parts.push(`${label} ${n}`)
          } else if (result.code === 'day_not_empty') {
            parts.push(`${label} already has posts`)
          } else {
            parts.push(`${label} failed`)
          }
        }
        setScheduleMessage(parts.join(' · '))
        load()
      } finally {
        setScheduling(false)
      }
    },
    [load, scheduleBrandIds],
  )

  if (error && days.length === 0) {
    return (
      <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
    )
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/week" title="This week">
        {isDayMode
          ? 'One day at a time — edit render mode and copy before lodge.'
          : isAll
            ? 'Every post across operating brands — past three days, today through the next six, and undated backlog.'
            : 'Every post for this brand — past three days, today through the next six, and undated backlog.'}
      </PageIntro>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            isDayMode && dateIso === sastTodayIso() ? 'border-ac bg-ac/15 text-ac' : 'border-bd text-tx2'
          }`}
          onClick={() => setDeskParams('day', sastTodayIso())}
        >
          Today
        </button>
        <button
          type="button"
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            isDayMode && dateIso === sastTomorrowIso() ? 'border-ac bg-ac/15 text-ac' : 'border-bd text-tx2'
          }`}
          onClick={() => setDeskParams('day', sastTomorrowIso())}
        >
          Tomorrow
        </button>
        <input
          type="date"
          value={isDayMode ? dateIso : sastTodayIso()}
          onChange={(e) => setDeskParams('day', e.target.value || sastTodayIso())}
          className="rounded-full border border-bd bg-bg px-3 py-1 text-xs text-tx"
          aria-label="Pick a day"
        />
        <button
          type="button"
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            !isDayMode ? 'border-ac bg-ac/15 text-ac' : 'border-bd text-tx2'
          }`}
          onClick={() => setDeskParams('week', dateIso)}
        >
          Week
        </button>
        {isDayMode ? (
          <button
            type="button"
            data-testid="generate-oneshots"
            title={oneshotTitle}
            disabled={oneshotDisabled || oneshotBusy}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${
              oneshotDisabled ? 'border-bd text-tx3' : 'border-gold bg-gold/15 text-gold'
            }`}
            onClick={() => void generateOneshots()}
          >
            Generate one-shots
          </button>
        ) : null}
      </div>
      {oneshotMsg ? <p className="text-xs text-tx2">{oneshotMsg}</p> : null}

      <PartialBrandLoadStrip failures={failures} onRetry={load} />

      {!isDayMode && pastDays.length > 0 ? (
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
              <DaySection key={day.date} day={day} waitForReads={waitForLoad} />
            ))}
          </div>
        </details>
      ) : null}

      <div className="space-y-5">
        {daySections.map((day) => (
          <DaySection
            key={day.date}
            day={day}
            waitForReads={waitForLoad}
            editable={isDayMode}
            postTypeByBrand={postTypeByBrand}
            onRefresh={load}
            scheduleBrandIds={isDayMode ? scheduleBrandIds : undefined}
            onSchedule={isDayMode ? handleScheduleDay : undefined}
            scheduling={scheduling}
            scheduleMessage={scheduleMessage}
          />
        ))}
      </div>

      {!isDayMode && (undated.length > 0 || undatedTotal > 0) ? (
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
                key={`${post.brand_id ?? ''}:${post.calendar_id}`}
                post={post}
                dayDate=""
                weekday=""
                waitForReads={waitForLoad}
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
