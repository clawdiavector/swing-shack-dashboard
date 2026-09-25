import { Images } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { BrandSwitch, useBrandScope } from '../components/BrandSwitch'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, QueueItemThumb } from '../components/ui'
import {
  fetchBrandVisuals,
  fetchBrands,
  resolveAssetUrl,
  runSocialIngest,
  type BrandVisualDriveItem,
  type BrandVisualReferenceItem,
  type BrandVisualSocialItem,
} from '../lib/api'
import {
  DRIVE_GROUP_ORDER,
  groupDriveAssets,
  patchDriveReference,
  patchSocialReference,
  platformTabLabel,
  shortCaption,
  socialEngagement,
  socialPlatformsFromChannels,
  toggleBrandReference,
  type SocialPlatform,
} from '../lib/brandVisuals'
import { formatDateStamp } from '../lib/stamp'

type Toast = { tone: 'green' | 'red'; text: string }

function ReferenceMarkButton({
  marked,
  busy,
  onClick,
}: {
  marked: boolean
  busy: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      disabled={busy}
      aria-pressed={marked}
      aria-label={marked ? 'Unmark reference' : 'Mark as reference'}
      onClick={onClick}
      className={`rounded-lg px-2 py-1 text-[11px] font-semibold ${
        marked ? 'bg-yel/20 text-yel' : 'bg-white/10 text-tx2 hover:bg-white/15'
      }`}
    >
      {marked ? 'Reference' : 'Mark as reference'}
    </button>
  )
}

function SocialTile({
  item,
  busy,
  onToggle,
}: {
  item: BrandVisualSocialItem
  busy: boolean
  onToggle: () => void
}) {
  const thumb = resolveAssetUrl(item.thumb_url)
  const when = formatDateStamp(item.posted_at)
  const engagement = socialEngagement(item.metrics)
  return (
    <article className="glass flex min-w-[160px] flex-col overflow-hidden rounded-2xl border border-white/10">
      <div className="relative aspect-square min-h-[160px] w-full bg-bg2">
        {thumb ? (
          <QueueItemThumb
            src={thumb}
            alt={item.caption || item.id}
            className="h-full w-full rounded-none border-0 object-cover"
          />
        ) : null}
        {item.is_reference ? (
          <span className="absolute top-2 left-2 rounded-md bg-yel/90 px-1.5 py-0.5 text-[10px] font-bold text-bg">
            Ref
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        {when ? <p className="text-xs text-tx3">{when}</p> : null}
        <p className="line-clamp-2 text-sm text-tx">{shortCaption(item.caption)}</p>
        {engagement ? <p className="text-xs text-tx3">{engagement}</p> : null}
        <div className="mt-auto pt-2">
          <ReferenceMarkButton marked={!!item.is_reference} busy={busy} onClick={onToggle} />
        </div>
      </div>
    </article>
  )
}

function DriveTile({
  item,
  busy,
  onToggle,
}: {
  item: BrandVisualDriveItem
  busy: boolean
  onToggle: () => void
}) {
  const thumb = resolveAssetUrl(item.thumb_url)
  return (
    <article className="glass flex min-w-[160px] flex-col overflow-hidden rounded-2xl border border-white/10">
      <div className="relative aspect-square min-h-[160px] w-full bg-bg2">
        {thumb ? (
          <QueueItemThumb
            src={thumb}
            alt={item.id}
            className="h-full w-full rounded-none border-0 object-cover"
          />
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <p className="truncate text-sm font-medium text-tx">{item.id}</p>
        <div className="mt-auto pt-2">
          <ReferenceMarkButton marked={!!item.is_reference} busy={busy} onClick={onToggle} />
        </div>
      </div>
    </article>
  )
}

export type BrandVisualsLayoutProps = {
  brandLabel: string
  needBrand: boolean
  platforms: SocialPlatform[]
  platform: SocialPlatform
  onPlatformChange: (id: string) => void
  social: BrandVisualSocialItem[]
  drive: BrandVisualDriveItem[]
  references: BrandVisualReferenceItem[]
  loading: boolean
  ingestBusy: boolean
  toggleBusyId: string | null
  toast: Toast | null
  onRunIngest: () => void
  onToggleSocial: (item: BrandVisualSocialItem) => void
  onToggleDrive: (item: BrandVisualDriveItem) => void
}

export function BrandVisualsLayout({
  brandLabel,
  needBrand,
  platforms,
  platform,
  onPlatformChange,
  social,
  drive,
  references,
  loading,
  ingestBusy,
  toggleBusyId,
  toast,
  onRunIngest,
  onToggleSocial,
  onToggleDrive,
}: BrandVisualsLayoutProps) {
  const platformOptions = platforms.map((p) => ({ id: p, label: platformTabLabel(p) }))
  const driveGroups = groupDriveAssets(drive)

  return (
    <div className="space-y-8">
      {toast ? (
        <p
          className={`rounded-2xl border px-4 py-3 text-sm ${
            toast.tone === 'green'
              ? 'border-green/40 bg-green/10 text-green'
              : 'border-red/40 bg-red/10 text-red'
          }`}
          role="status"
        >
          {toast.text}
        </p>
      ) : null}

      {needBrand ? (
        <div className="glass rounded-2xl border border-white/10 p-6">
          <p className="text-sm text-tx2">Pick a brand to load social history, Drive assets, and references.</p>
          <div className="mt-4">
            <BrandSwitch variant="bar" />
          </div>
        </div>
      ) : null}

      {!needBrand ? (
        <>
          <section className="space-y-4">
            <h2 className="font-display text-2xl font-semibold md:text-3xl">
              {platformTabLabel(platform)}
            </h2>
            {platforms.length > 1 ? (
              <FilterChips options={platformOptions} value={platform} onChange={onPlatformChange} />
            ) : null}
            {loading ? <p className="text-sm text-tx3">Loading visuals…</p> : null}
            {!loading && social.length === 0 ? (
              <div className="glass rounded-2xl border border-dashed border-white/15 p-8 text-center">
                <p className="text-sm text-tx2">Run social ingest to pull the last posts for {brandLabel}.</p>
                <button
                  type="button"
                  title="Pull latest Instagram and Facebook posts for this brand."
                  disabled={ingestBusy}
                  onClick={onRunIngest}
                  className="mt-4 inline-flex items-center rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-60"
                >
                  Run social ingest
                </button>
              </div>
            ) : null}
            {!loading && social.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                {social.map((item) => (
                  <SocialTile
                    key={`${item.platform}-${item.id}`}
                    item={item}
                    busy={toggleBusyId === item.id}
                    onToggle={() => onToggleSocial(item)}
                  />
                ))}
              </div>
            ) : null}
          </section>

          <section className="space-y-4">
            <h2 className="font-display text-2xl font-semibold md:text-3xl">Brand assets (Drive)</h2>
            {drive.length === 0 && !loading ? (
              <p className="text-sm text-tx3">No Drive images in brand-directory yet.</p>
            ) : null}
            {DRIVE_GROUP_ORDER.map((group) => {
              const rows = driveGroups[group]
              if (!rows.length) return null
              return (
                <div key={group} className="space-y-3">
                  <h3 className="font-display text-lg font-semibold text-tx2">{group}</h3>
                  <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                    {rows.map((item) => (
                      <DriveTile
                        key={item.id}
                        item={item}
                        busy={toggleBusyId === item.id}
                        onToggle={() => onToggleDrive(item)}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </section>

          <section className="space-y-4">
            <h2 className="font-display text-2xl font-semibold md:text-3xl">References</h2>
            {references.length === 0 ? (
              <p className="text-sm text-tx3">Marked references appear here with platform and pillar chips.</p>
            ) : (
              <div className="flex gap-3 overflow-x-auto pb-2">
                {references.map((ref) => {
                  const thumb = resolveAssetUrl(ref.thumb_url)
                  return (
                    <article
                      key={ref.id}
                      className="glass w-[180px] shrink-0 overflow-hidden rounded-2xl border border-white/10"
                    >
                      <div className="aspect-square min-h-[160px] bg-bg2">
                        {thumb ? (
                          <QueueItemThumb
                            src={thumb}
                            alt={ref.label || ref.id}
                            className="h-full w-full rounded-none border-0 object-cover"
                          />
                        ) : null}
                      </div>
                      <div className="flex flex-wrap gap-1 p-2">
                        {ref.platform ? <Badge tone="blue">{ref.platform}</Badge> : null}
                        {ref.pillar ? <Badge tone="gold">{ref.pillar}</Badge> : null}
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  )
}

export function BrandVisuals() {
  const { isAll, scope } = useBrandScope()
  const brandId = isAll ? null : scope
  const [platforms, setPlatforms] = useState<SocialPlatform[]>(['instagram', 'facebook'])
  const [platform, setPlatform] = useState<SocialPlatform>('instagram')
  const [social, setSocial] = useState<BrandVisualSocialItem[]>([])
  const [drive, setDrive] = useState<BrandVisualDriveItem[]>([])
  const [references, setReferences] = useState<BrandVisualReferenceItem[]>([])
  const [loading, setLoading] = useState(false)
  const [ingestBusy, setIngestBusy] = useState(false)
  const [toggleBusyId, setToggleBusyId] = useState<string | null>(null)
  const [toast, setToast] = useState<Toast | null>(null)
  const [brandLabel, setBrandLabel] = useState('')

  useEffect(() => {
    if (!brandId) return
    fetchBrands()
      .then((payload) => {
        const rec = payload.brands?.[brandId]
        const label = rec?.display_name || rec?.label || rec?.name || brandId
        setBrandLabel(label)
        const ch = socialPlatformsFromChannels(rec?.publish_channels)
        setPlatforms(ch.length ? ch : ['instagram', 'facebook'])
        setPlatform((prev) => (ch.includes(prev) ? prev : ch[0] || 'instagram'))
      })
      .catch(() => {
        setBrandLabel(brandId)
        setPlatforms(['instagram', 'facebook'])
      })
  }, [brandId])

  const loadVisuals = useCallback(() => {
    if (!brandId) return
    setLoading(true)
    fetchBrandVisuals(brandId, platform)
      .then((payload) => {
        setSocial(payload.social || [])
        setDrive(payload.drive || [])
        setReferences(payload.references || [])
      })
      .catch((err: Error) => {
        setToast({ tone: 'red', text: err.message || 'Could not load visuals.' })
      })
      .finally(() => setLoading(false))
  }, [brandId, platform])

  useEffect(() => {
    loadVisuals()
  }, [loadVisuals])

  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(() => setToast(null), 6000)
    return () => window.clearTimeout(t)
  }, [toast])

  const handleRunIngest = useCallback(async () => {
    if (!brandId) return
    setIngestBusy(true)
    try {
      const result = await runSocialIngest(brandId)
      const verdict = (result.data?.verdict as string) || (result.ok ? 'OK' : 'FAILED')
      setToast({
        tone: result.ok ? 'green' : 'red',
        text: result.ok ? `Social ingest finished (${verdict}).` : `Social ingest failed (${verdict}).`,
      })
      loadVisuals()
    } catch (err) {
      setToast({
        tone: 'red',
        text: err instanceof Error ? err.message : 'Social ingest request failed.',
      })
    } finally {
      setIngestBusy(false)
    }
  }, [brandId, loadVisuals])

  const handleToggleSocial = useCallback(
    async (item: BrandVisualSocialItem) => {
      if (!brandId) return
      const was = !!item.is_reference
      setSocial((rows) => patchSocialReference(rows, item.id, !was))
      setToggleBusyId(item.id)
      try {
        await toggleBrandReference(brandId, item.id, was, 'social', item.platform)
        loadVisuals()
      } catch (err) {
        setSocial((rows) => patchSocialReference(rows, item.id, was))
        setToast({
          tone: 'red',
          text: err instanceof Error ? err.message : 'Reference toggle failed.',
        })
      } finally {
        setToggleBusyId(null)
      }
    },
    [brandId, loadVisuals],
  )

  const handleToggleDrive = useCallback(
    async (item: BrandVisualDriveItem) => {
      if (!brandId) return
      const was = !!item.is_reference
      setDrive((rows) => patchDriveReference(rows, item.id, !was))
      setToggleBusyId(item.id)
      try {
        await toggleBrandReference(brandId, item.id, was, 'drive')
        loadVisuals()
      } catch (err) {
        setDrive((rows) => patchDriveReference(rows, item.id, was))
        setToast({
          tone: 'red',
          text: err instanceof Error ? err.message : 'Reference toggle failed.',
        })
      } finally {
        setToggleBusyId(null)
      }
    },
    [brandId, loadVisuals],
  )

  const platformChange = useCallback(
    (id: string) => {
      if (id === 'instagram' || id === 'facebook') setPlatform(id)
    },
    [],
  )

  return (
    <div className="space-y-6">
      <PageIntro icon={Images} here="/brand/visuals" title="Brand visuals">
        Social history, Drive assets, and curated references for one brand at a time.
      </PageIntro>
      <BrandVisualsLayout
        brandLabel={brandLabel || brandId || 'brand'}
        needBrand={!brandId}
        platforms={platforms}
        platform={platform}
        onPlatformChange={platformChange}
        social={social}
        drive={drive}
        references={references}
        loading={loading}
        ingestBusy={ingestBusy}
        toggleBusyId={toggleBusyId}
        toast={toast}
        onRunIngest={handleRunIngest}
        onToggleSocial={handleToggleSocial}
        onToggleDrive={handleToggleDrive}
      />
    </div>
  )
}
