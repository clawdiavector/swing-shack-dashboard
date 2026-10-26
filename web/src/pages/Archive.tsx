import { ArchiveRestore, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { Tip } from '../components/ui'
import {
  fetchBrandArchive,
  restoreBrandArchiveItem,
  type ArchivedItem,
} from '../lib/api'
import { actorName } from '../lib/plan'

function formatStamp(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso.replace('Z', '+00:00'))
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10)
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function Archive() {
  const { brandId } = useBrand()
  const scope = brandId ?? ''
  const [items, setItems] = useState<ArchivedItem[]>([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback(() => {
    if (!scope) return
    setLoading(true)
    setMsg('')
    fetchBrandArchive(scope)
      .then((r) => {
        if (r.error) setMsg(r.error)
        setItems(r.items || [])
      })
      .catch((e: unknown) => setMsg(e instanceof Error ? e.message : 'Could not load archive'))
      .finally(() => setLoading(false))
  }, [scope])

  useEffect(() => {
    load()
  }, [load])

  async function restore(item: ArchivedItem) {
    const name = actorName()
    if (!name) {
      setMsg('Your name is needed so the audit log knows who restored this.')
      return
    }
    const key = `${item.kind}:${item.id}`
    setBusyId(key)
    const r = await restoreBrandArchiveItem(
      scope,
      {
        kind: item.kind,
        id: item.id,
        suggestion_key: item.suggestion_key,
      },
      name,
    )
    setBusyId('')
    if (!r.ok) {
      setMsg(r.error || 'Restore failed.')
      return
    }
    load()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 pb-16">
      <PageIntro icon={ArchiveRestore} here="/archive" title="Archive">
        Archived drafts, plans, and suggestions for this brand. Each row shows when it will be
        purged for good (30 days after archive). Restore brings it back to the live lists.
      </PageIntro>

      {!scope ? (
        <p className="text-sm text-tx3">Choose a brand first.</p>
      ) : (
        <>
          {msg ? <p className="text-sm text-red">{msg}</p> : null}
          {loading ? (
            <p className="inline-flex items-center gap-2 text-sm text-tx2">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </p>
          ) : null}
          {!loading && items.length === 0 ? (
            <HeroPanel icon={ArchiveRestore} kicker="Archive" title="Nothing archived">
              <p className="text-sm text-tx2">Use Archive on a draft, plan, or calendar suggestion.</p>
            </HeroPanel>
          ) : null}
          <ul className="space-y-3">
            {items.map((item) => {
              const bid = `${item.kind}:${item.id}`
              return (
                <li
                  key={bid}
                  className="glass flex flex-col gap-2 rounded-2xl border border-white/10 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-bold tracking-wide text-tx3 uppercase">{item.kind}</p>
                    <p className="truncate font-semibold text-tx">{item.title || item.id}</p>
                    <p className="text-xs text-tx3">
                      Archived {formatStamp(item.archived_at)} by {item.archived_by || 'operator'}
                    </p>
                    <p className="text-xs text-tx2">
                      <Tip text="After this date the daily purge job deletes it permanently.">
                        Purge after {formatStamp(item.purge_at)}
                      </Tip>
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={busyId === bid}
                    onClick={() => void restore(item)}
                    className="shrink-0 rounded-full border border-yel/40 bg-yel/15 px-4 py-2 text-xs font-semibold text-yel hover:bg-yel/25 disabled:opacity-60"
                  >
                    {busyId === bid ? 'Restoring…' : 'Restore'}
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
