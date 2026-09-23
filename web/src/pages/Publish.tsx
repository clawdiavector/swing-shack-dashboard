import { CheckCircle2, Link2, MapPin, Rocket, Send, Share2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { Badge, Button, ClassicLink, IconTile, QueueItem, StatCard, Tip } from '../components/ui'
import {
  fetchPostizOverview,
  fetchPublishMode,
  fetchToday,
  type PostizOverview,
  type PublishMode,
  type TodayCounts,
  type TodayPanel,
} from '../lib/api'
import { pickQueueTitle } from '../lib/publishCaption'
import { formatStamp } from '../lib/stamp'

export function Publish() {
  const { brandId } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [counts, setCounts] = useState<TodayCounts | null>(null)
  const [publishMode, setPublishMode] = useState<PublishMode | null>(null)
  const [overview, setOverview] = useState<PostizOverview | null>(null)
  const [queueErr, setQueueErr] = useState('')

  useEffect(() => {
    fetchPublishMode()
      .then(setPublishMode)
      .catch(() => setPublishMode(null))
  }, [])

  useEffect(() => {
    fetchToday(brandId)
      .then((panel) => {
        setData(panel)
        setCounts(panel.counts || null)
      })
      .catch(() => {
        setData(null)
        setCounts(null)
      })
  }, [brandId])

  useEffect(() => {
    fetchPostizOverview()
      .then((o) => {
        setOverview(o)
        setQueueErr('')
      })
      .catch((e: Error) => {
        setOverview(null)
        setQueueErr(e.message || 'Could not load the publish queue')
      })
  }, [])

  const drafts = overview?.queue || []
  const scheduled = overview?.scheduled || []
  const next = drafts[0] || scheduled[0]
  const nextTitle = next ? pickQueueTitle(next) : counts?.approved ? 'Open the publish queue' : 'Nothing approved yet'
  const nextMeta = next
    ? `${next.platform || 'post'}${next.scheduled_date ? ` · ${formatStamp(next.scheduled_date)}` : next.publish_timestamp ? ` · ${formatStamp(next.publish_timestamp)}` : ''}`
    : 'Clear Review first, then this queue fills.'

  const queueCountLabel =
    drafts.length > 0 && overview?.queue_total && overview.queue_total > drafts.length
      ? `${drafts.length} of ${overview.queue_total}`
      : String(drafts.length)

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Rocket}
        badge="Go live"
        here="/publish"
        title="Queued to ship"
        actions={
          publishMode ? (
            <Badge tone={publishMode.mode === 'live' ? 'red' : 'gold'}>
              {publishMode.label || publishMode.mode} — sandbox applies to dispatch job only
            </Badge>
          ) : null
        }
      >
        Approved work, GBP, Postiz, and accounts — one screen. Approve still does not publish.
      </PageIntro>

      <p className="text-sm text-tx3">
        <ClassicLink href="/?page=publish" label="publish" />
      </p>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          icon={CheckCircle2}
          label="Approved"
          value={counts?.approved ?? '—'}
          hint="Ready, not live"
          tone="mute"
          stamp={data?.ts}
          stampKind="as_of"
        />
        <StatCard
          icon={Send}
          label="Queued"
          value={counts?.scheduled ?? '—'}
          hint="On the calendar"
          tone="gold"
          stamp={data?.ts}
          stampKind="as_of"
        />
        <StatCard
          to="/results"
          icon={Rocket}
          label="Shipped"
          value={counts?.published ?? '—'}
          hint="Already live"
          tone="green"
          stamp={data?.ts}
          stampKind="as_of"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(380px,1fr)]">
        <HeroPanel icon={Rocket} kicker="Next to ship" title={nextTitle} meta={nextMeta}>
          <Button to="/publish/queue" icon={Send} tip="Open the publish queue. Approve still does not ship.">
            Publish queue
          </Button>
          <Button to="/publish/gbp" icon={MapPin} tone="ghost" tip="Open Google Business Profile drafts and listings.">
            GBP
          </Button>
        </HeroPanel>
        <section>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="font-display text-xl font-semibold">Ready lane</h2>
            {overview && !queueErr ? <Badge tone="green">{queueCountLabel}</Badge> : null}
          </div>
          <p className="mb-3 text-xs text-tx3">
            All brands — the publish queue reads flat publish files and does not follow the brand switch.
          </p>
          <ul className="space-y-2">
            {overview === null && !queueErr ? (
              <>
                <li className="h-16 animate-pulse rounded-2xl bg-bg3" />
                <li className="h-16 animate-pulse rounded-2xl bg-bg3" />
                <li className="h-16 animate-pulse rounded-2xl bg-bg3" />
              </>
            ) : null}
            {queueErr ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Could not load the publish queue ({queueErr}) —{' '}
                <Tip text="Open the full publish queue.">
                  <Link to="/publish/queue" className="font-semibold text-ac">
                    open it directly
                  </Link>
                </Tip>
                .
              </li>
            ) : null}
            {!queueErr && overview
              ? drafts.slice(0, 6).map((row) => {
                  const id = String(row.publish_id || row.item_id || '')
                  return (
                    <QueueItem
                      key={id || pickQueueTitle(row)}
                      to={`/publish/queue?tab=drafts&item=${encodeURIComponent(id)}`}
                      badge={String(row.platform || 'post')}
                      tone="green"
                      title={pickQueueTitle(row)}
                      stamp={row.scheduled_date || row.publish_timestamp}
                    />
                  )
                })
              : null}
            {!queueErr && overview && drafts.length === 0 ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Nothing in the publish queue — approve something in Review, then push it to Postiz.
              </li>
            ) : null}
          </ul>
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">Channels</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <IconTile href="/publish/queue" icon={Send} label="Publish queue" hint="What ships next" />
          <IconTile href="/?page=postiz" icon={Rocket} label="Postiz" hint="Scheduler" />
          <IconTile href="/publish/gbp" icon={MapPin} label="GBP" hint="Google Business Profile" />
          <IconTile href="/?page=gmb" icon={MapPin} label="GBP drafts" hint="Pending listings" />
          <IconTile href="/publish/socials" icon={Share2} label="Socials" hint="What went live" />
          <IconTile href="/ops?tab=accounts" icon={Link2} label="Accounts" hint="Connected channels" />
        </div>
      </section>
    </div>
  )
}
