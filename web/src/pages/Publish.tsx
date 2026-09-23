import { CheckCircle2, Link2, MapPin, Rocket, Send, Share2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { Badge, Button, ClassicLink, IconTile, QueueItem, StatCard, Tip } from '../components/ui'
import {
  fetchPublishMode,
  fetchSandboxQueue,
  fetchToday,
  resolveAssetUrl,
  type PublishMode,
  type SandboxQueueItem,
  type TodayCounts,
  type TodayPanel,
} from '../lib/api'
import { sandboxRowId, sandboxTitle } from '../lib/sandboxRow'
import { formatStamp } from '../lib/stamp'

export function Publish() {
  const { brandId } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [counts, setCounts] = useState<TodayCounts | null>(null)
  const [publishMode, setPublishMode] = useState<PublishMode | null>(null)
  const [sandbox, setSandbox] = useState<SandboxQueueItem[]>([])
  const [sandboxTotal, setSandboxTotal] = useState(0)
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
    fetchSandboxQueue(brandId)
      .then((payload) => {
        setSandbox(payload.items || [])
        setSandboxTotal(payload.total_pending ?? payload.items?.length ?? 0)
        setQueueErr('')
      })
      .catch((e: Error) => {
        setSandbox([])
        setSandboxTotal(0)
        setQueueErr(e.message || 'Could not load sandbox queue')
      })
  }, [brandId])

  const next = sandbox[0]
  const nextTitle = next ? sandboxTitle(next) : counts?.approved ? 'Queue from the shelf' : 'Nothing queued yet'
  const nextMeta = next
    ? `${next.platform || 'post'} · ${next.brand_id || brandId || 'brand'}${next.created_at ? ` · ${formatStamp(next.created_at)}` : ''}`
    : 'Approve on Review, shelf it, then queue here — still sandbox only.'

  const queueCountLabel =
    sandbox.length > 0 && sandboxTotal > sandbox.length
      ? `${sandbox.length} of ${sandboxTotal}`
      : String(sandbox.length)

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Rocket}
        badge="Sandbox queue"
        here="/publish"
        title="Queued to ship"
        actions={
          publishMode ? (
            <Badge tone={publishMode.mode === 'live' ? 'red' : 'gold'}>
              {publishMode.label || publishMode.mode || 'SANDBOX'}
            </Badge>
          ) : (
            <Badge tone="gold">SANDBOX</Badge>
          )
        }
      >
        Sandbox publish queue — image, caption, platform. Approve on Review does not publish live.
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
          label="Sandbox queued"
          value={sandboxTotal || '—'}
          hint="Pending rows"
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
        <HeroPanel icon={Rocket} kicker="Next in sandbox" title={nextTitle} meta={nextMeta}>
          <Button to="/shelf" icon={Send} tip="Approved drafts waiting to be queued.">
            Shelf
          </Button>
          <Button to="/publish/queue" icon={Send} tone="ghost" tip="Legacy Postiz publish queue (flat files).">
            Postiz queue
          </Button>
          <Button to="/publish/gbp" icon={MapPin} tone="ghost" tip="Open Google Business Profile drafts and listings.">
            GBP
          </Button>
        </HeroPanel>
        <section>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="font-display text-xl font-semibold">Sandbox lane</h2>
            {!queueErr ? <Badge tone="gold">{queueCountLabel}</Badge> : null}
          </div>
          <p className="mb-3 text-xs text-tx3">
            Pending sandbox rows for {brandId || 'all brands'} — receipts only until dispatch runs.
          </p>
          <ul className="space-y-2">
            {queueErr ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Could not load sandbox queue ({queueErr}).
              </li>
            ) : null}
            {!queueErr
              ? sandbox.map((row) => {
                  const id = sandboxRowId(row)
                  const thumb = resolveAssetUrl(row.image_url || row.image_path)
                  const caption = String(row.caption || row.caption_preview || '').trim()
                  return (
                    <QueueItem
                      key={id || sandboxTitle(row)}
                      to={id ? `/publish/sandbox/${encodeURIComponent(id)}` : undefined}
                      tip="Open the sandbox preview — mock only, nothing goes live."
                      badge={String(row.platform || 'post')}
                      tone="gold"
                      title={sandboxTitle(row)}
                      meta={[row.brand_id, caption.slice(0, 80)].filter(Boolean).join(' · ')}
                      stamp={row.created_at}
                      thumb={thumb || undefined}
                      thumbAlt={caption.slice(0, 80) || id}
                    />
                  )
                })
              : null}
            {!queueErr && sandbox.length === 0 ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Sandbox queue is empty —{' '}
                <Tip text="Approved drafts not yet queued.">
                  <Link to="/shelf" className="font-semibold text-ac">
                    check the shelf
                  </Link>
                </Tip>
                .
              </li>
            ) : null}
          </ul>
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">Channels</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <IconTile href="/publish/queue" icon={Send} label="Postiz queue" hint="Legacy flat files" />
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
