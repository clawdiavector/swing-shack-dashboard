import { ArrowLeft, Rocket } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { PlatformMock } from '../../components/PlatformMock'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import { fetchSandboxQueue, resolveAssetUrl, type SandboxQueueItem } from '../../lib/api'
import { PLATFORM_TABS, resolvePlatformTab, type PlatformTab } from '../../lib/platformMock'
import { matchSandboxRow, sandboxTitle } from '../../lib/sandboxRow'
import { formatStamp } from '../../lib/stamp'

export function SandboxPreview() {
  const { brandId } = useBrand()
  const { queueId = '' } = useParams()
  const id = decodeURIComponent(queueId)
  const [row, setRow] = useState<SandboxQueueItem | null>(null)
  const [missReason, setMissReason] = useState<'loading' | 'not_found' | 'limit' | 'error' | ''>('')
  const [loadErr, setLoadErr] = useState('')
  const [tab, setTab] = useState<PlatformTab>('instagram')

  useEffect(() => {
    if (!id) {
      setMissReason('not_found')
      return
    }
    let live = true
    setMissReason('loading')
    setRow(null)
    setLoadErr('')

    function findIn(items: SandboxQueueItem[] | undefined) {
      return items?.find((r) => matchSandboxRow(r, id)) ?? null
    }

    fetchSandboxQueue(brandId, 200)
      .then((payload) => {
        if (!live) return
        const hit = findIn(payload.items)
        if (hit) {
          setRow(hit)
          setTab(resolvePlatformTab(hit.platform))
          setMissReason('')
          return
        }
        return fetchSandboxQueue(undefined, 200).then((all) => {
          if (!live) return
          const hitAll = findIn(all.items)
          if (hitAll) {
            setRow(hitAll)
            setTab(resolvePlatformTab(hitAll.platform))
            setMissReason('')
            return
          }
          const total = all.total_pending ?? all.items?.length ?? 0
          setMissReason(total > 200 ? 'limit' : 'not_found')
        })
      })
      .catch((e: Error) => {
        if (live) {
          setLoadErr(e.message || 'Could not load sandbox queue')
          setMissReason('error')
        }
      })

    return () => {
      live = false
    }
  }, [brandId, id])

  const caption = String(row?.caption || row?.caption_preview || '').trim()
  const imageUrl = resolveAssetUrl(row?.image_url || row?.image_path || '')

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Rocket}
        badge="SANDBOX"
        here="/publish"
        title={row ? sandboxTitle(row) : missReason === 'loading' ? 'Opening…' : 'Sandbox preview'}
      >
        Mock only — image and caption as queued. Nothing goes live from this page.
      </PageIntro>

      <Tip text="Back to Publish.">
        <Link
          to="/publish"
          title="Back to Publish."
          className="glass-pill inline-flex items-center gap-1.5 rounded-full border border-white/10 px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={2.5} />
          Publish
        </Link>
      </Tip>

      {loadErr ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">{loadErr}</p>
      ) : null}

      {missReason === 'limit' ? (
        <p className="text-sm text-yel">
          That row is not in the first 200 pending — open{' '}
          <ClassicLink href="/?page=publish" label="publish" /> for the full list.
        </p>
      ) : null}

      {missReason === 'not_found' && !loadErr ? (
        <div className="rounded-2xl border border-dashed border-bd px-4 py-8 text-sm text-tx3">
          No pending sandbox row matches this link. It may have shipped or been removed.
        </div>
      ) : null}

      {row ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm text-tx2">
            {row.brand_id ? <Badge tone="mute">{row.brand_id}</Badge> : null}
            {row.platform ? <Badge tone="gold">{row.platform}</Badge> : null}
            {row.created_at ? (
              <span>
                <span className="text-tx3">Landed</span> {formatStamp(row.created_at)}
              </span>
            ) : null}
            {row.would_publish_at ? (
              <span>
                <span className="text-tx3">Goes out</span> {formatStamp(row.would_publish_at)}
              </span>
            ) : null}
          </div>

          <FilterChips options={PLATFORM_TABS} value={tab} onChange={(next) => setTab(next as PlatformTab)} />

          <PlatformMock platform={tab} imageUrl={imageUrl} caption={caption} brandId={row.brand_id} />
        </>
      ) : null}
    </div>
  )
}
