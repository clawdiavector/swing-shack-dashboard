import { CheckCircle2, Link2, MapPin, Rocket, Send, Share2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrandChip } from '../components/BrandChip'
import { useBrandScope } from '../components/BrandSwitch'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
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
import { fanOutPayloads, type FanOutFailure } from '../lib/fanOut'
import { sumCounts } from '../lib/mergeCounts'
import { sandboxGoesOutIso, sandboxRowId, sandboxTitle } from '../lib/sandboxRow'
import { formatStamp } from '../lib/stamp'

export function Publish() {
  const { isAll, brandIds, scope } = useBrandScope()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [counts, setCounts] = useState<TodayCounts | null>(null)
  const [publishMode, setPublishMode] = useState<PublishMode | null>(null)
  const [sandbox, setSandbox] = useState<SandboxQueueItem[]>([])
  const [sandboxTotal, setSandboxTotal] = useState(0)
  const [queueErr, setQueueErr] = useState('')
  const [failures, setFailures] = useState<FanOutFailure[]>([])

  useEffect(() => {
    fetchPublishMode()
      .then(setPublishMode)
      .catch(() => setPublishMode(null))
  }, [])

  function loadPanelAndQueue() {
    const run = async () => {
      setFailures([])
      if (isAll) {
        const [todayFan, queueFan] = await Promise.all([
          fanOutPayloads(brandIds, (bid) => fetchToday(bid)),
          fanOutPayloads(brandIds, (bid) => fetchSandboxQueue(bid)),
        ])
        setFailures([...todayFan.failures, ...queueFan.failures])
        const todayCounts = sumCounts(todayFan.payloads.map((p) => p.payload.counts))
        setCounts(todayCounts as TodayCounts)
        setData(todayFan.payloads[0]?.payload ?? null)
        const items = queueFan.payloads.flatMap(({ brandId: bid, payload }) =>
          (payload.items || []).map((row) => ({
            ...row,
            brand_id: row.brand_id ?? bid,
          })),
        )
        setSandbox(items)
        const totalPending = queueFan.payloads.reduce(
          (n, p) => n + (p.payload.total_pending ?? p.payload.items?.length ?? 0),
          0,
        )
        setSandboxTotal(totalPending)
        setQueueErr('')
        return
      }
      const brandId = scope === 'all' ? undefined : scope
      fetchToday(brandId)
        .then((panel) => {
          setData(panel)
          setCounts(panel.counts || null)
        })
        .catch(() => {
          setData(null)
          setCounts(null)
        })
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
    }
    void run()
  }

  useEffect(() => {
    loadPanelAndQueue()
  }, [isAll, brandIds, scope])

  const next = sandbox[0]
  const nextTitle = next ? sandboxTitle(next) : counts?.approved ? 'Queue from the shelf' : 'Nothing queued yet'
  const nextMeta = next
    ? `${next.platform || 'post'} · ${next.brand_id || 'brand'}${next.created_at ? ` · ${formatStamp(next.created_at)}` : ''}`
    : 'Approve on Review, shelf it, then queue here — still sandbox only.'

  const releasedWaiting = sandbox.filter((row) => row.human_approved)
  const notReleased = sandbox.filter((row) => !row.human_approved)
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
          <div className="flex flex-wrap gap-2">
            {publishMode ? (
              <Badge tone={publishMode.mode === 'live' ? 'red' : 'gold'}>
                Mode: {publishMode.label || publishMode.mode || 'SANDBOX'}
              </Badge>
            ) : (
              <Badge tone="gold">Mode: SANDBOX</Badge>
            )}
            <Badge tone={publishMode?.auto_release ? 'green' : 'mute'}>
              Auto release: {publishMode?.auto_release ? 'on' : 'off'}
            </Badge>
          </div>
        }
      >
        Sandbox publish queue — image, caption, platform. Approve on Review does not publish live.
      </PageIntro>

      <PartialBrandLoadStrip failures={failures} onRetry={loadPanelAndQueue} />

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
            Pending sandbox rows for {isAll ? 'all brands' : scope} — receipts only until dispatch runs.
          </p>
          {queueErr ? (
            <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
              Could not load sandbox queue ({queueErr}).
            </p>
          ) : null}
          {!queueErr ? (
            <>
              <h3 className="mb-2 text-sm font-semibold text-tx2">Released, waiting to dispatch</h3>
              <ul className="mb-4 space-y-2">
                {releasedWaiting.map((row) => {
                  const id = sandboxRowId(row)
                  const thumb = resolveAssetUrl(row.image_url || row.image_path)
                  const caption = String(row.caption || row.caption_preview || '').trim()
                  const goesOut = sandboxGoesOutIso(row)
                  const platform = String(row.platform || 'post')
                  return (
                    <QueueItem
                      key={`rel-${id || sandboxTitle(row)}`}
                      to={id ? `/publish/sandbox/${encodeURIComponent(id)}` : undefined}
                      tip="Human-approved — dispatch job writes the receipt."
                      badge="released"
                      tone="green"
                      channelBadge={platform}
                      title={sandboxTitle(row)}
                      meta={[isAll ? null : row.brand_id, caption.slice(0, 80)].filter(Boolean).join(' · ')}
                      footer={isAll ? <BrandChip brandId={row.brand_id} show /> : undefined}
                      stamp={goesOut || row.created_at}
                      stampKind={goesOut ? 'goes_out' : 'created'}
                      dateOnly={Boolean(goesOut)}
                      thumb={thumb || undefined}
                      thumbAlt={caption.slice(0, 80) || id}
                    />
                  )
                })}
                {releasedWaiting.length === 0 ? (
                  <li className="rounded-2xl border border-dashed border-bd px-4 py-4 text-sm text-tx3">
                    No released rows yet — use Release now on the Shelf.
                  </li>
                ) : null}
              </ul>
              <h3 className="mb-2 text-sm font-semibold text-tx2">Not released yet</h3>
              <ul className="space-y-2">
                {notReleased.map((row) => {
                  const id = sandboxRowId(row)
                  const thumb = resolveAssetUrl(row.image_url || row.image_path)
                  const caption = String(row.caption || row.caption_preview || '').trim()
                  const goesOut = sandboxGoesOutIso(row)
                  const platform = String(row.platform || 'post')
                  return (
                    <QueueItem
                      key={`nr-${id || sandboxTitle(row)}`}
                      to={id ? `/publish/sandbox/${encodeURIComponent(id)}` : undefined}
                      tip="QC passed but not human-released."
                      badge="sandbox"
                      tone="gold"
                      channelBadge={platform}
                      title={sandboxTitle(row)}
                      meta={[isAll ? null : row.brand_id, caption.slice(0, 80)].filter(Boolean).join(' · ')}
                      footer={isAll ? <BrandChip brandId={row.brand_id} show /> : undefined}
                      stamp={goesOut || row.created_at}
                      stampKind={goesOut ? 'goes_out' : 'created'}
                      dateOnly={Boolean(goesOut)}
                      thumb={thumb || undefined}
                      thumbAlt={caption.slice(0, 80) || id}
                    />
                  )
                })}
                {notReleased.length === 0 && releasedWaiting.length === 0 ? (
                  <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                    Sandbox queue is empty —{' '}
                    <Tip text="Scheduled posts waiting for release.">
                      <Link to="/shelf" className="font-semibold text-ac">
                        check the shelf
                      </Link>
                    </Tip>
                    .
                  </li>
                ) : null}
              </ul>
            </>
          ) : null}
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
