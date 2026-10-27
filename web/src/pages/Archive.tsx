import { ArchiveRestore, Loader2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { Tip } from '../components/ui'
import {
  fetchBrandArchive,
  purgeExpiredBrandArchive,
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

  const now = Date.now()
  const expired = items.filter((item) => {
    const t = new Date((item.purge_at || '').replace('Z', '+00:00')).getTime()
    return Number.isFinite(t) && t <= now
  })

  async function deleteExpired() {
    const name = actorName()
    if (!name) {
      setMsg('Your name is needed so the audit log knows who deleted these.')
      return
    }
    const ask = `Delete ${expired.length} archived item(s) older than 60 days for good? This cannot be undone.`
    if (!window.confirm(ask)) return
    setBusyId('purge')
    const r = await purgeExpiredBrandArchive(scope, name)
    setBusyId('')
    if (!r.ok) {
      setMsg(r.error || 'Delete failed.')
      return
    }
    // load() clears the message, so reload first and say what happened after.
    load()
    setMsg(
      r.dry_run
        ? `Dry run: ${r.total ?? 0} item(s) would be deleted. Deleting is off until ARCHIVE_PURGE_LIVE is set.`
        : `Deleted ${r.total ?? 0} item(s).`,
    )
  }

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
        Archived drafts, plans, and suggestions for this brand. Nothing is archived or deleted
        automatically: items stay here for 60 days, then you can delete them with the button below.
        Restore brings one back to the live lists.
      </PageIntro>

      {!scope ? (
        <p className="text-sm text-tx3">Choose a brand first.</p>
      ) : (
        <>
          {msg ? <p className="text-sm text-red">{msg}</p> : null}
          {expired.length ? (
            <button
              type="button"
              disabled={busyId === 'purge'}
              onClick={() => void deleteExpired()}
              data-testid="archive-delete-expired"
              className="rounded-full border border-red/40 bg-red/10 px-4 py-2 text-xs font-semibold text-red hover:bg-red/20 disabled:opacity-60"
            >
              {busyId === 'purge' ? 'Deleting…' : `Delete ${expired.length} expired (older than 60 days)`}
            </button>
          ) : null}
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
                      <Tip text="Kept until this date. After it, Delete expired removes it for good. Nothing deletes on its own.">
                        Can be deleted after {formatStamp(item.purge_at)}
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
