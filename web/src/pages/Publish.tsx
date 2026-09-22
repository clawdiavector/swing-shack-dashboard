import { CheckCircle2, Link2, MapPin, Rocket, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { Button, IconTile, QueueItem, StatCard } from '../components/ui'
import { fetchToday, type TodayCard, type TodayCounts, type TodayPanel } from '../lib/api'

export function Publish() {
  const { brandId } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [counts, setCounts] = useState<TodayCounts | null>(null)

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

  const ready = (data?.cards || []).filter(
    (c) => c.kind === 'publish' || c.kind === 'post' || /approv|ready|queue/i.test(c.label || ''),
  ) as TodayCard[]
  const list = ready.length ? ready : ((data?.cards || []).slice(0, 6) as TodayCard[])
  const next = list[0]

  return (
    <div className="space-y-6">
      <PageIntro icon={Rocket} badge="Go live" here="/publish" title="Queued to ship">
        Approved work, GBP, Postiz, and accounts — one screen. Approve still does not publish.
      </PageIntro>

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
        <HeroPanel
          icon={Rocket}
          kicker="Next to ship"
          title={next?.title || (counts?.approved ? 'Open the publish queue' : 'Nothing approved yet')}
          meta={next?.label || 'Clear Review first, then this queue fills.'}
        >
          <Button href="/?page=publish" icon={Send} tip="Open the publish queue. Approve still does not ship.">
            Publish queue
          </Button>
          <Button href="/?page=gbp" icon={MapPin} tone="ghost" tip="Open Google Business Profile drafts and listings.">
            GBP
          </Button>
        </HeroPanel>
        <section>
          <h2 className="mb-3 font-display text-xl font-semibold">Ready lane</h2>
          <ul className="space-y-2">
            {list.slice(1, 7).map((card) => (
              <QueueItem
                key={`${card.kind}-${card.id}`}
                to={`/review/${encodeURIComponent(card.id)}`}
                badge={card.label}
                tone="green"
                title={card.title}
                stamp={card.stamp || card.updatedAt}
              />
            ))}
            {list.length <= 1 ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Queue is thin — approve something in Review.
              </li>
            ) : null}
          </ul>
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">Channels</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <IconTile href="/?page=publish" icon={Send} label="Publish queue" hint="What ships next" />
          <IconTile href="/?page=postiz" icon={Rocket} label="Postiz" hint="Scheduler" />
          <IconTile href="/?page=gbp" icon={MapPin} label="GBP" hint="Google Business Profile" />
          <IconTile href="/?page=gmb" icon={MapPin} label="GBP drafts" hint="Pending listings" />
          <IconTile href="/ops?tab=accounts" icon={Link2} label="Accounts" hint="Connected channels" />
        </div>
      </section>
    </div>
  )
}
