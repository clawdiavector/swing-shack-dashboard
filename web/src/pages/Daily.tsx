import {
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Inbox,
  MapPin,
  PenLine,
  Rocket,
  Send,
  Share2,
  Sparkles,
  Sun,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrandSwitch, useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { InsightPostThumb, insightPostThumbSrc } from '../components/InsightPostThumb'
import { Badge, Button, IconTile, QueueItem, StatCard, Tip } from '../components/ui'
import {
  fetchInbox,
  fetchLayers,
  fetchLearn,
  fetchToday,
  fetchTopPosts,
  fetchVisualLibrary,
  inboxItemThumbUrl,
  inboxMediaTag,
  resolveAssetUrl,
  type InboxItem,
  type InsightPost,
  type InsightsPosts,
  type LayerEntry,
  type LayersPayload,
  type LearnSummary,
  type TodayPanel,
} from '../lib/api'
import { reviewType } from '../lib/reviewType'
import type { BriefAction } from '../lib/api'
import { formatStamp } from '../lib/stamp'

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function briefLabel(a: BriefAction) {
  const act = a.action || ''
  if (act === 'create_brief') return 'Write brief'
  if (act === 'review_brief') return 'Review brief'
  if (act === 'view_brief') return 'Brief ready'
  if (act.startsWith('watch_or_ignore:')) {
    return (act.split(':')[1] || '').toUpperCase() === 'WATCH' ? 'Watching' : 'Parked'
  }
  return 'Brief'
}

function briefTone(a: BriefAction): 'gold' | 'green' | 'mute' {
  const act = a.action || ''
  if (act === 'create_brief' || act === 'review_brief') return 'gold'
  if (act === 'view_brief') return 'green'
  return 'mute'
}

function briefTip(a: BriefAction) {
  const act = a.action || ''
  if (act === 'create_brief') return 'This date cleared the gate and has no brief yet.'
  if (act === 'review_brief') {
    const rev =
      a.brief_revision != null ? ` Revision ${a.brief_revision}.` : ''
    return `A draft brief is waiting on your read.${rev}`
  }
  if (act === 'view_brief') return 'The brief for this date is written.'
  if (act.startsWith('watch_or_ignore:')) return 'On the watchlist — not worth a brief yet.'
  return 'Brief opportunity on the calendar.'
}

function layerOf(layers: LayersPayload | null, id: string): LayerEntry {
  return (layers?.layers || {})[id] || {}
}

function morningTitle(opts: {
  layers: LayersPayload | null
  learn: LearnSummary | null
  best?: InsightPost
  waiting: number
}): string {
  const l4 = layerOf(opts.layers, 'L4')
  const l7 = layerOf(opts.layers, 'L7')
  const stale = l4.stale ?? 0
  const pending = l4.pending ?? opts.waiting
  const winners = opts.learn?.headline?.winners ?? l7.winners ?? 0
  if (stale > 0) {
    return stale === 1
      ? 'One piece has sat too long. That’s the call this morning.'
      : `${stale} pieces have sat too long. That’s the call this morning.`
  }
  if (opts.best?.verdict === 'Top performer' && opts.best.caption_excerpt) {
    return `A post is beating the average. Repeat that shape.`
  }
  if (winners > 0) {
    return `${winners} winning recipe${winners === 1 ? '' : 's'} from last week — spend against those.`
  }
  if (pending > 0) {
    return `${pending} decisions still need a yes or no.`
  }
  if ((l7.verdict || '').toUpperCase() === 'NEVER') {
    return 'Learn hasn’t scored last week. We don’t yet know what worked.'
  }
  return 'Desk is quiet. Open Studio if you want a new draft.'
}

export function Daily() {
  const { brandId } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [layers, setLayers] = useState<LayersPayload | null>(null)
  const [learn, setLearn] = useState<LearnSummary | null>(null)
  const [posts, setPosts] = useState<InsightPost[]>([])
  const [libraryThumbs, setLibraryThumbs] = useState<Array<{ key: string; src: string }>>([])
  const [inboxItems, setInboxItems] = useState<InboxItem[] | null>(null)
  const [insightMeta, setInsightMeta] = useState<InsightsPosts['_meta']>()
  const [error, setError] = useState('')

  function load(brand?: string) {
    setInboxItems(null)
    fetchToday(brand)
      .then(setData)
      .catch((err: Error) => setError(err.message))
    fetchLayers(brand)
      .then(setLayers)
      .catch(() => setLayers(null))
    fetchLearn()
      .then(setLearn)
      .catch(() => setLearn(null))
    fetchTopPosts(brand)
      .then((payload) => {
        setPosts(payload.posts || [])
        setInsightMeta(payload._meta)
      })
      .catch(() => {
        setPosts([])
        setInsightMeta(undefined)
      })
    fetchInbox('pending', brand)
      .then((payload) => setInboxItems(payload.items || []))
      .catch(() => setInboxItems([]))
    fetchVisualLibrary(brand || 'swing-shack')
      .then((payload) => {
        const rows = (payload.images || []) as Array<{
          filename?: string
          url?: string
          thumbnail_data_url?: string
        }>
        const thumbs: Array<{ key: string; src: string }> = []
        for (const row of rows) {
          const src =
            (row.thumbnail_data_url && String(row.thumbnail_data_url)) ||
            resolveAssetUrl(row.url)
          if (!src) continue
          thumbs.push({ key: row.filename || src, src })
          if (thumbs.length >= 6) break
        }
        setLibraryThumbs(thumbs)
      })
      .catch(() => setLibraryThumbs([]))
  }

  useEffect(() => {
    load(brandId)
  }, [brandId])

  const counts = data?.counts
  const waiting = counts?.review ?? 0
  const drafts = counts?.draft ?? 0
  const tickerItems = (inboxItems || []).slice(0, 7)
  const igWorkedPosts = posts.slice(0, 3)
  const igWithImmediateThumb = igWorkedPosts.filter((p) => Boolean(insightPostThumbSrc(p)))
  const igWithPermalinkOnly = igWorkedPosts.filter(
    (p) => !insightPostThumbSrc(p) && Boolean(p.permalink),
  )
  const libraryFillCount = Math.max(
    0,
    3 - igWithImmediateThumb.length - igWithPermalinkOnly.length,
  )
  const workedLibraryThumbs = libraryThumbs.slice(0, libraryFillCount)
  const workedMixedCaption =
    (igWithImmediateThumb.length > 0 || igWithPermalinkOnly.length > 0) &&
    workedLibraryThumbs.length > 0
  const asOf = data?.ts
  const best = posts[0]
  const l1 = layerOf(layers, 'L1')
  const l3 = layerOf(layers, 'L3')
  const l4 = layerOf(layers, 'L4')
  const l6 = layerOf(layers, 'L6')
  const l7 = layerOf(layers, 'L7')
  const briefActions = (data?.brief_actions?.actions || []).slice(0, 4)
  const pulse = useMemo(() => {
    const rows: { label: string; value: string }[] = []
    if (best?.plain_english) {
      const verdict = best.verdict || 'Best post'
      const cleaned = best.plain_english
        .replace(/^[^\dA-Za-z]+/, '')
        .replace(/^(Top performer|Underperformer|Average)\.?\s*/i, '')
      rows.push({
        label: verdict,
        value: cleaned || best.plain_english,
      })
    } else if (best?.caption_excerpt) {
      rows.push({
        label: 'Best post',
        value: `“${best.caption_excerpt}”${best.engagementRate != null ? ` · ${best.engagementRate.toFixed(2)}% engagement` : ''}`,
      })
    } else if (insightMeta?.total_scanned) {
      const avg = insightMeta.average_engagement
      rows.push({
        label: 'Instagram',
        value: `Scanned ${insightMeta.total_scanned} posts${avg != null ? ` · ${avg.toFixed(2)}% average engagement` : ''}. Nothing is beating the pack yet.`,
      })
    } else {
      rows.push({
        label: 'Instagram',
        value: insightMeta?.reason || 'No scored posts yet — interpret hasn’t ranked last week’s feed.',
      })
    }
    const winners = learn?.headline?.winners ?? l7.winners ?? 0
    const recipes = learn?.headline?.recipes ?? l7.recipes ?? 0
    if (winners > 0 || recipes > 0) {
      rows.push({
        label: 'Learn',
        value: `${winners} winner${winners === 1 ? '' : 's'}, ${recipes} recipe${recipes === 1 ? '' : 's'} the desk can spend against.`,
      })
    } else if (learn?.headline?.proposal_gate === 'insufficient_data') {
      rows.push({
        label: 'Learn',
        value: 'Not enough scored posts to pick a recipe yet.',
      })
    } else {
      rows.push({
        label: 'Learn',
        value: 'No scored winners yet — last week hasn’t been interpreted.',
      })
    }
    const silent = l1.never ?? 0
    const late = l1.late ?? 0
    const stuck = l1.stuck ?? 0
    const failed = l1.failed ?? 0
    let overnight = 'Checking overnight jobs…'
    if (layers) {
      overnight = 'Overnight jobs landed. Figures are current.'
      if (silent > 0) {
        overnight = `${silent} jobs never reported. Treat today’s numbers as yesterday’s.`
      } else if (failed > 0) {
        overnight = `${failed} overnight job${failed === 1 ? '' : 's'} failed. Figures may be incomplete.`
      } else if (stuck > 0 || late > 0) {
        overnight = `${late + stuck} job${late + stuck === 1 ? '' : 's'} late or stuck. Refresh before you brief anyone.`
      } else if ((l1.verdict || '').toUpperCase() === 'NEVER') {
        overnight = 'Overnight jobs haven’t checked in. Treat today’s numbers as stale.'
      } else if ((l1.verdict || 'OK').toUpperCase() !== 'OK') {
        overnight = `Data layer is ${(l1.verdict || 'quiet').toLowerCase()}.`
      }
    }
    rows.push({
      label: 'Data overnight',
      value: overnight,
    })
    return rows
  }, [best, insightMeta, layers, learn, l1, l7])
  const calls = useMemo(() => {
    const rows: { label: string; value: string; to: string }[] = []
    const stale = l4.stale ?? 0
    const pending = l4.pending ?? waiting
    if (stale > 0) {
      rows.push({
        label: 'Going stale',
        value: `${stale} review${stale === 1 ? '' : 's'} sat past the SLA.`,
        to: '/review',
      })
    }
    if (pending > 0) {
      rows.push({
        label: 'Waiting on a call',
        value: `${pending} piece${pending === 1 ? '' : 's'} still need a yes or no.`,
        to: '/review',
      })
    }
    const queued = l6.queue_approved_ready
    const approved = counts?.approved ?? 0
    let ship = 'Nothing approved is queued to go live.'
    if (queued != null && queued > 0) {
      ship = `${queued} approved and sitting in the publish queue.`
    } else if (approved > 0) {
      ship = `${approved} approved, not yet sitting in the publish queue.`
    }
    rows.push({
      label: 'Ready to ship',
      value: ship,
      to: '/publish',
    })
    const quiet = Boolean(layers) && ((l3.never ?? 0) > 0 || (l3.reporting ?? 0) === 0)
    if (quiet) {
      rows.push({
        label: 'Interpret',
        value: 'Scout / interpret hasn’t checked in. No fresh opportunities this morning.',
        to: '/calendar',
      })
    }
    return rows.slice(0, 4)
  }, [layers, l3, l4, l6, waiting, counts])

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
      >
        {data?.summary || 'Loading your decisions for today…'}
      </PageIntro>

      {error ? (
        <p className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">
          Could not load the brief. {error}
        </p>
      ) : null}

      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          to="/review"
          icon={Inbox}
          label="Waiting on you"
          value={data ? waiting : '—'}
          hint="Approve, edit, or send back"
          tone="gold"
          stamp={asOf}
          stampKind="as_of"
        />
        <StatCard
          to="/create"
          icon={PenLine}
          label="Drafts"
          value={data ? drafts : '—'}
          hint="In studio, not reviewed yet"
          tone="mute"
          stamp={asOf}
          stampKind="as_of"
        />
        <StatCard
          to="/calendar"
          icon={CalendarDays}
          label="Today"
          value={data ? (counts?.scheduled ?? 0) : '—'}
          hint="Scheduled to go live"
          tone="mute"
          stamp={asOf}
          stampKind="as_of"
        />
        <StatCard
          to="/publish"
          icon={Send}
          label="Ready"
          value={data ? (counts?.approved ?? 0) : '—'}
          hint="Approved · queued to ship"
          tone="mute"
          stamp={asOf}
          stampKind="as_of"
        />
        <StatCard
          to="/results"
          icon={CheckCircle2}
          label="This week"
          value={data ? (counts?.published ?? 0) : '—'}
          hint="Shipped · outcomes in Results"
          tone="green"
          stamp={asOf}
          stampKind="as_of"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(380px,1fr)]">
        <HeroPanel
          icon={Rocket}
          kicker="Do this right now"
          title={
            data
              ? morningTitle({ layers, learn, best, waiting })
              : 'Reading last night’s numbers…'
          }
          meta={asOf ? `As of ${formatStamp(asOf)}` : undefined}
          extra={
            <div className="grid gap-4 border-t border-bd pt-4 sm:grid-cols-2">
              <div>
                <p className="mb-2 text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase">
                  What the numbers say
                </p>
                <ul className="space-y-2">
                  {pulse.map((f) => (
                    <li key={f.label} className="glass rounded-xl border-[1.5px] border-white/10 px-3 py-2">
                      <p className="text-[12px] font-semibold tracking-wide text-tx3 uppercase">{f.label}</p>
                      <p className="text-sm leading-snug font-medium">{f.value}</p>
                    </li>
                  ))}
                </ul>
                {briefActions.length ? (
                  <div className="mt-3 border-t border-bd pt-3">
                    <p className="mb-2 text-[12px] font-semibold tracking-wide text-tx3 uppercase">
                      Briefs waiting
                    </p>
                    <ul className="flex flex-wrap gap-2">
                      {briefActions.map((a, i) => (
                        <li key={a.event_key || a.name || i}>
                          <Tip text={briefTip(a)}>
                            <span className="glass-pill inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5">
                              <Badge tone={briefTone(a)}>{briefLabel(a)}</Badge>
                              <span className="text-sm font-medium text-tx2">{a.name || a.event_key}</span>
                            </span>
                          </Tip>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
              <div>
                <p className="mb-2 text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase">
                  What needs a call
                </p>
                <ul className="space-y-2">
                  {calls.map((row, i) => (
                    <li key={row.label}>
                      <Link
                        to={row.to}
                        title={`Open ${row.label}: ${row.value}`}
                        className="glass flex items-start gap-2 rounded-xl border-[1.5px] border-white/10 px-3 py-2 hover:border-ac/40"
                      >
                        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-yel/15 text-[13px] font-bold text-yel">
                          {i + 1}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[12px] font-semibold tracking-wide text-tx3 uppercase">
                            {row.label}
                          </span>
                          <span className="block text-sm leading-snug font-medium">{row.value}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          }
        >
          <Button to="/review" icon={Inbox} tip="Open the review inbox and work the queue.">
            Clear my desk
          </Button>
          <Button to="/create" icon={Sparkles} tone="ghost" tip="Open Studio to start a new draft.">
            Go to studio
          </Button>
        </HeroPanel>

        <section>
          <div className="mb-3 flex items-end justify-between">
            <h2 className="font-display text-xl font-semibold">Today ticker</h2>
            <Tip text="See every piece waiting on you.">
            <Link
              to="/review"
              title="See every piece waiting on you."
              className="inline-flex items-center gap-0.5 text-sm font-semibold text-ac"
            >
              All waiting
              <ChevronRight className="h-4 w-4" strokeWidth={2.5} />
            </Link>
            </Tip>
          </div>
          <ul className="space-y-2">
            {tickerItems.map((item) => {
              const thumb = inboxItemThumbUrl(item)
              const media = inboxMediaTag(item)
              return (
              <QueueItem
                key={item.id}
                to={`/review/${encodeURIComponent(item.id)}`}
                badge={item.sla_state === 'stale' ? 'stale' : media.label}
                tone={item.sla_state === 'stale' ? 'gold' : media.tone}
                title={item.title || item.summary || item.id}
                meta={[reviewType(item.type).label, item.brand_id]
                  .filter(Boolean)
                  .join(' · ')}
                stamp={item.created_at}
                stampKind="created"
                thumb={thumb || undefined}
                thumbAlt={item.title || item.id}
              />
              )
            })}
            {inboxItems && tickerItems.length === 0 ? (
              <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
                Nothing else waiting — go to Studio if you want a new draft.
              </li>
            ) : null}
            {inboxItems === null && !error ? (
              <>
                <li className="h-16 animate-pulse rounded-2xl bg-bg3" />
                <li className="h-16 animate-pulse rounded-2xl bg-bg3" />
                <li className="h-16 animate-pulse rounded-2xl bg-bg3" />
              </>
            ) : null}
          </ul>
          {igWorkedPosts.length || workedLibraryThumbs.length ? (
            <div className="mt-4">
              <p className="mb-2 text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase">
                What worked
                {workedMixedCaption ? (
                  <span className="ml-2 font-normal normal-case tracking-normal text-tx3">
                    Instagram + visual library
                  </span>
                ) : workedLibraryThumbs.length && !igWorkedPosts.length ? (
                  <span className="ml-2 font-normal normal-case tracking-normal text-tx3">
                    Visual library
                  </span>
                ) : null}
              </p>
              <ul className="flex flex-wrap gap-2">
                {igWorkedPosts.map((p, i) => {
                  const key = p.id || String(i)
                  const to = p.id
                    ? `/results/worked?tab=posts&post=${encodeURIComponent(p.id)}`
                    : '/results/worked?tab=posts'
                  return (
                    <li key={key}>
                      <Tip
                        text={`${p.verdict || 'Recent post'}${p.engagementRate != null ? ` · ${p.engagementRate.toFixed(2)}% engagement` : ''} — open it in Results.`}
                      >
                        <Link
                          to={to}
                          className="block rounded-xl border border-bd hover:border-ac/40"
                        >
                          <InsightPostThumb post={p} thumbKey={key} />
                        </Link>
                      </Tip>
                    </li>
                  )
                })}
                {workedLibraryThumbs.map((row) => (
                  <li key={`lib-${row.key}`}>
                    <Tip text="Visual library photo — open the library in Studio.">
                      <Link
                        to="/create/images?tab=library"
                        className="block overflow-hidden rounded-xl border border-bd hover:border-ac/40"
                      >
                        <img
                          src={row.src}
                          alt=""
                          loading="lazy"
                          className="h-16 w-16 object-cover"
                        />
                      </Link>
                    </Tip>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">Shortcuts</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <IconTile to="/publish/socials" icon={Share2} label="Socials" hint="What’s live for this brand" />
          <IconTile to="/publish/gbp" icon={MapPin} label="GBP" hint="Google Business Profile" />
          <IconTile to="/create/post" icon={Sparkles} label="Build a post" hint="Jump straight into studio" />
          <IconTile to="/results/week" icon={CheckCircle2} label="This week" hint="Weekly report" />
        </div>
      </section>
    </div>
  )
}
