import { Calendar, Library, Rocket } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useBrandScope } from '../components/BrandSwitch'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
import { PageIntro } from '../components/chrome'
import { PostCard } from '../components/posting/PostCard'
import { Badge, Button, StatCard } from '../components/ui'
import { fetchPublishMode, fetchShelf, type PublishMode } from '../lib/api'
import { fanOutPayloads, mergeShelfPayloads, type FanOutFailure } from '../lib/fanOut'
import { useLoadGate } from '../lib/useLoadGate'
import { formatGoesOut, type ShelfPayload } from '../lib/postingWeek'

export function Shelf() {
  const { isAll, brandIds, scope } = useBrandScope()
  const { trackLoad, waitForLoad } = useLoadGate()
  const [data, setData] = useState<ShelfPayload | null>(null)
  const [publishMode, setPublishMode] = useState<PublishMode | null>(null)
  const [error, setError] = useState('')
  const [failures, setFailures] = useState<FanOutFailure[]>([])

  const load = useCallback(() => {
    const run = async (): Promise<void> => {
      setFailures([])
      if (isAll) {
        const { payloads, failures: fails } = await fanOutPayloads(brandIds, (brandId) => fetchShelf(brandId))
        setFailures(fails)
        const merged = mergeShelfPayloads(payloads, brandIds)
        setData(merged)
        setError(merged.error || '')
        return
      }
      const brandId = scope === 'all' ? undefined : scope
      fetchShelf(brandId)
        .then((payload) => {
          setData(payload)
          setError(payload.error || '')
        })
        .catch((err: Error) => setError(err.message))
    }
    trackLoad(run())
  }, [isAll, brandIds, scope, trackLoad])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    fetchPublishMode()
      .then(setPublishMode)
      .catch(() => setPublishMode(null))
  }, [])

  const counts = data?.counts
  const autoOff = publishMode?.auto_release === false || publishMode?.auto_release == null

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Library}
        here="/shelf"
        title="Scheduled"
        actions={
          <div className="flex flex-wrap gap-2">
            {publishMode ? (
              <Badge tone={publishMode.mode === 'live' ? 'red' : 'gold'}>
                Mode: {publishMode.label || publishMode.mode || 'sandbox'}
              </Badge>
            ) : null}
            <Badge tone={autoOff ? 'mute' : 'green'}>
              Auto release: {publishMode?.auto_release ? 'on' : 'off'}
            </Badge>
          </div>
        }
      >
        Approved posts with a go-live date — release when ready. Sandbox only until Kyle enables live.
      </PageIntro>

      <PartialBrandLoadStrip failures={failures} onRetry={load} />

      {autoOff ? (
        <p className="text-xs text-tx3">Auto-release is off — Release now is the only way out today.</p>
      ) : null}

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{error}</p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Calendar}
          label="Scheduled"
          value={counts?.scheduled ?? '—'}
          hint="Waiting for release"
          tone="green"
        />
        <StatCard
          icon={Rocket}
          label="Releasable today"
          value={counts?.releasable_today ?? '—'}
          hint="Go-live is today"
          tone="gold"
        />
        <StatCard
          icon={Library}
          label="Released waiting"
          value={counts?.released ?? '—'}
          hint="Awaiting dispatch"
          tone="mute"
        />
        <StatCard
          icon={Rocket}
          label="Released today"
          value={counts?.released_today ?? '—'}
          hint="Human releases"
          tone="mute"
        />
      </div>

      {data?.date_groups?.map((group) => (
        <section key={group.date}>
          <div className="mb-3 flex items-end justify-between">
            <h2 className="font-display text-xl font-semibold">
              {formatGoesOut(group.date)}
            </h2>
            <Badge tone="green">{group.posts.length}</Badge>
          </div>
          <ul className="space-y-2">
            {group.posts.map((post) => (
              <PostCard
                key={`${post.brand_id ?? ''}:${post.calendar_id}`}
                post={post}
                dayDate={group.date}
                weekday=""
                onRefresh={load}
                waitForReads={waitForLoad}
              />
            ))}
          </ul>
        </section>
      ))}

      {data?.undated && data.undated.length > 0 ? (
        <section>
          <div className="mb-3 flex items-end justify-between">
            <h2 className="font-display text-xl font-semibold">No date</h2>
            <Badge tone="gold">{data.undated.length}</Badge>
          </div>
          <ul className="space-y-2">
            {data.undated.map((post) => (
              <PostCard
                key={`${post.brand_id ?? ''}:${post.calendar_id}`}
                post={post}
                dayDate=""
                weekday=""
                onRefresh={load}
                waitForReads={waitForLoad}
              />
            ))}
          </ul>
        </section>
      ) : null}

      {!error &&
      (data?.date_groups?.every((g) => g.posts.length === 0) ?? true) &&
      (data?.undated?.length ?? 0) === 0 ? (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
          Nothing scheduled — approve drafts in Review first, then they land here.
        </p>
      ) : null}

      <Button to="/publish" icon={Rocket} tip="Open Publish to see the sandbox queue.">
        Open publish
      </Button>
      <p className="text-xs text-tx3">
        View draft detail in{' '}
        <Link to="/review" className="font-semibold text-ac">
          Review
        </Link>
        .
      </p>
    </div>
  )
}
