import { Megaphone, Sun } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import '../fun.css'
import { FunTile, Mascot } from '../components/fun'
import { burstConfetti } from '../lib/confetti'
import { BrandSwitch, useBrand, useBrandScope } from '../components/BrandSwitch'
import { MailToday } from '../components/MailToday'
import { MomentsToday } from '../components/MomentsToday'
import { NextToApprove } from '../components/NextToApprove'
import { AlertBanner } from './calendar/planning/AlertBanner'
import { PartialBrandLoadStrip } from '../components/PartialBrandLoadStrip'
import { PageIntro } from '../components/chrome'
import { countTiles, deskLine, useFourCounts } from '../lib/fourCounts'
import { fetchInbox, fetchToday, type InboxItem, type TodayPanel } from '../lib/api'
import { isCandidateItem } from '../lib/inboxCandidates'
import { fanOutPayloads, type FanOutFailure } from '../lib/fanOut'
import { sumCounts } from '../lib/mergeCounts'

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// The shorter Today (5 Nov 2026): counts, the soonest dates, the next drafts, Herman's ideas
// and two moments. Stories, What worked, socials and shortcuts live on their own tabs, so this
// page no longer loads ops layers, top posts, learn or the visual library.
export function Daily() {
  const { brandId: focusBrandId, brandLabel } = useBrand()
  const { isAll, brandIds, scope } = useBrandScope()
  // The four counts every page shows (Scheduled and Sent come from the shelf and send queue).
  const four = useFourCounts(isAll ? '' : focusBrandId || '')
  const [data, setData] = useState<TodayPanel | null>(null)
  const [inboxItems, setInboxItems] = useState<InboxItem[] | null>(null)
  const [error, setError] = useState('')
  const [failures, setFailures] = useState<FanOutFailure[]>([])

  function load() {
    // Inbox rows stay null if a brand fails, so the counts show '—', never a 0 that reads as an empty desk.
    setInboxItems(null)
    const runAll = async () => {
      setFailures([])
      // Sequential fan-outs (plan §3.5) — at most one 3-brand wave at a time.
      const todayFan = await fanOutPayloads(brandIds, (bid) => fetchToday(bid))
      const inboxFan = await fanOutPayloads(brandIds, (bid) => fetchInbox('pending', bid))
      setFailures([...todayFan.failures, ...inboxFan.failures])
      const counts = sumCounts(todayFan.payloads.map((p) => p.payload.counts))
      const cards = todayFan.payloads.flatMap((p) => p.payload.cards || [])
      setData({
        ok: true,
        counts: counts as TodayPanel['counts'],
        cards,
        ts: todayFan.payloads[0]?.payload.ts,
      })
      const inboxMerged = inboxFan.payloads.flatMap(({ brandId: bid, payload }) =>
        (payload.items || []).map((item) => ({
          ...item,
          brand_id: item.brand_id ?? bid,
        })),
      )
      inboxMerged.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      if (inboxFan.failures.length === 0) setInboxItems(inboxMerged)
    }

    if (isAll) {
      void runAll().catch((err: Error) => setError(err.message))
    } else {
      const brand = scope === 'all' ? undefined : scope
      fetchToday(brand)
        .then(setData)
        .catch((err: Error) => setError(err.message))
      fetchInbox('pending', brand)
        .then((payload) => setInboxItems(payload.items || []))
        .catch((err: Error) => setError(err.message || 'The inbox did not load.'))
    }
  }

  useEffect(() => {
    load()
  }, [isAll, brandIds, scope, focusBrandId])

  // Counted from the same rows Inbox and Approve drafts list, so the numbers
  // here match the pages they open.
  const candidatesWaiting = inboxItems ? inboxItems.filter(isCandidateItem).length : null
  const draftRows = (inboxItems || []).filter((i) => (i.type || '').toLowerCase() === 'draft_asset')
  const draftsWaiting = inboxItems ? draftRows.length : null
  const summary =
    data && inboxItems
      ? deskLine({
          to_approve: draftsWaiting || 0,
          dates_to_decide: candidatesWaiting || 0,
          scheduled: four?.scheduled ?? 0,
          sent_this_week: four?.sent_this_week ?? 0,
        })
      : data?.summary || ''
  const waitingTotal = (draftsWaiting || 0) + (candidatesWaiting || 0)
  const deskClear = Boolean(data && inboxItems && waitingTotal === 0)
  const celebrated = useRef(false)
  useEffect(() => {
    if (!deskClear || celebrated.current) return
    celebrated.current = true
    let seen = false
    try {
      seen = sessionStorage.getItem('cos-desk-cleared') === '1'
      sessionStorage.setItem('cos-desk-cleared', '1')
    } catch {
      // Private window: celebrate once per page load instead.
    }
    if (!seen) burstConfetti(window.innerWidth / 2, window.innerHeight / 3, 140)
  }, [deskClear])
  const asOf = data?.ts

  return (
    <div className="space-y-6">
      <PageIntro
        icon={Sun}
        badge="Morning brief"
        here="/daily"
        title={
          <>
            {greeting()},{' '}
            <BrandSwitch variant="inline" />
          </>
        }
        actions={
          // A server-rendered page outside the SPA, so a plain link, not a router Link.
          <a
            href="/ads-brief"
            title="What the Meta ads need today, for both brands"
            className="glass-pill inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-tx hover:border-ac hover:text-ac"
          >
            <Megaphone className="h-4 w-4" />
            Ads brief
          </a>
        }
      >
        {summary || 'Pulling together today’s decisions…'}
      </PageIntro>

      <PartialBrandLoadStrip failures={failures} onRetry={load} />

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">
          Could not load the brief. {error}
        </p>
      ) : null}

      {deskClear ? (
        <div className="fun-cleared" role="status">
          <Mascot tone="green" />
          <div>
            <strong>Desk cleared. Look at you!</strong>
            <span>Nothing is waiting on you. Open Studio if you feel like making something.</span>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {countTiles(
          // The inbox numbers show as soon as the page has them; Scheduled and Sent follow.
          {
            ...(four ?? {}),
            ...(inboxItems ? { to_approve: draftsWaiting || 0, dates_to_decide: candidatesWaiting || 0 } : {}),
          },
        ).map((t) => (
          <FunTile
            key={t.key}
            to={t.to}
            label={t.label}
            value={t.value}
            hint={t.hint}
            tone={t.tone}
            stamp={asOf}
            stampKind="as_of"
          />
        ))}
      </div>

      {/* Shorter Today (5 Nov 2026): the soonest dates, the next drafts, Herman's ideas closed,
          two moments. Stories, What worked, socials and shortcuts live on their own tabs. */}
      <AlertBanner brandId={isAll ? '' : focusBrandId || ''} limit={3} />

      <NextToApprove items={draftRows} total={draftsWaiting || 0} onDone={load} />

      <MailToday brandId={isAll ? undefined : focusBrandId} />

      <MomentsToday brandLabel={isAll ? undefined : brandLabel} brandId={isAll ? undefined : focusBrandId} />
    </div>
  )
}
