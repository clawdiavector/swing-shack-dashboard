import { ImageIcon } from 'lucide-react'
import { useState, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { inboxAction, releaseMoment, resolveAssetUrl } from '../../lib/api'
import { BrandChip } from '../BrandChip'
import { useBrand, useBrandScope } from '../BrandSwitch'
import {
  formatGoesOut,
  formatSastClock,
  linkForPostState,
  nextActionFromStages,
  postFlagLabel,
  postingChannelLabel,
  postingWeekThumbUrl,
  postStateLabel,
  postStateTone,
  type PostingWeekPost,
} from '../../lib/postingWeek'
import { TemplateReferenceTag } from '../TemplateReferenceTag'
import { templateMetaFromPost } from '../../lib/templateMeta'
import { StageStepper } from './StageStepper'

function PostCardThumb({ imageUrl, title }: { imageUrl?: string | null; title: string }) {
  const [broken, setBroken] = useState(false)
  const raw = postingWeekThumbUrl(imageUrl)
  const src = raw ? resolveAssetUrl(raw) : null
  const showImage = Boolean(src) && !broken
  return (
    <div
      className={`relative flex w-[7.25rem] shrink-0 flex-col items-center gap-1 sm:w-[8rem] ${
        showImage ? '' : ''
      }`}
    >
      <div
        className={`flex aspect-[4/5] w-full items-center justify-center overflow-hidden rounded-xl border ${
          showImage ? 'border-bd bg-bg-2' : 'border-dashed border-bd bg-bg-2/50'
        }`}
      >
        {showImage ? (
          <img
            src={src!}
            alt=""
            className="max-h-full max-w-full object-contain"
            onError={() => setBroken(true)}
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-tx3" aria-hidden>
            <ImageIcon className="h-6 w-6" strokeWidth={1.75} />
          </span>
        )}
      </div>
      {broken ? (
        <span className="text-center text-[11px] font-semibold leading-tight text-red">Preview unavailable</span>
      ) : null}
      {!showImage && !broken && postStateNeedsImagePlaceholder(imageUrl) ? (
        <span className="text-center text-[11px] font-medium leading-tight text-tx3">No preview yet</span>
      ) : null}
      <span className="sr-only">{title}</span>
    </div>
  )
}

function postStateNeedsImagePlaceholder(imageUrl?: string | null) {
  return !String(imageUrl ?? '').trim()
}

export function PostCard({
  post,
  dayDate,
  weekday,
  onRefresh,
  waitForReads,
}: {
  post: PostingWeekPost
  dayDate: string
  weekday: string
  onRefresh?: () => void
  /** Plan §3.5 — await parent fan-out before lodge/release writes. */
  waitForReads?: () => Promise<void>
}) {
  const { brandId: focusBrandId } = useBrand()
  const { isAll } = useBrandScope()
  const rowBrandId = post.brand_id ?? focusBrandId ?? 'swing-shack'
  const [lodging, setLodging] = useState(false)
  const [releasing, setReleasing] = useState(false)
  const isCandidate = post.state === 'candidate'
  const isScheduled = post.state === 'scheduled'
  const isReleased = post.state === 'released'
  const isHoliday = post.flags?.includes('holiday')
  const noDate = post.flags?.includes('no_date')
  const to = isScheduled || isReleased ? undefined : linkForPostState(post)
  const clickable = Boolean(to) && !isHoliday

  async function handleLodge(event: MouseEvent) {
    event.preventDefault()
    event.stopPropagation()
    if (!post.inbox_item_id || noDate) return
    setLodging(true)
    await waitForReads?.()
    await inboxAction(post.inbox_item_id, 'approve', '', 'lodge')
    setLodging(false)
    onRefresh?.()
  }

  async function handleRelease(event: MouseEvent) {
    event.preventDefault()
    event.stopPropagation()
    if (!post.calendar_id) return
    setReleasing(true)
    await waitForReads?.()
    await releaseMoment(rowBrandId, post.calendar_id)
    setReleasing(false)
    onRefresh?.()
  }

  const channel = postingChannelLabel(post.primary_channel)
  const nextAction = post.next_action || nextActionFromStages(post.stages)
  const fixReason =
    post.state === 'needs_fix'
      ? post.needs_fix_reason || (nextAction !== 'Needs fix' ? nextAction : null) || 'Image or draft failed — open in Review'
      : null
  const goesOutAt = (post.sandbox ?? []).map((row) => row.would_publish_at).find((value) => value)
  const sastClock = formatSastClock(goesOutAt)
  const factLine = [formatGoesOut(dayDate, weekday), sastClock, nextAction].filter(Boolean).join(' · ')
  const tone = postStateTone(post.state)
  const templateMeta = templateMetaFromPost(post)
  const toneClass =
    tone === 'bad'
      ? 'border-red/40 text-red'
      : tone === 'warn'
        ? 'border-yel/40 text-yel'
        : tone === 'ok'
          ? 'border-green/40 text-green'
          : 'border-bd text-tx2'

  const inner = (
    <div className="flex flex-col gap-3">
      <div className="flex gap-3 md:gap-4">
        <PostCardThumb imageUrl={post.image_url} title={post.title} />
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <BrandChip brandId={rowBrandId} show={isAll} />
            <TemplateReferenceTag meta={templateMeta} onClickCapture={(e) => e.stopPropagation()} />
            <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${toneClass}`}>
              {postStateLabel(post.state)}
            </span>
            {post.flags?.map((flag) => (
              <span key={flag} className="text-xs text-tx3">
                {postFlagLabel(flag)}
              </span>
            ))}
            {isCandidate ? (
              <span className="text-xs font-medium text-tx3">Candidate · no image yet</span>
            ) : null}
          </div>
          <p className="font-display text-base font-semibold leading-snug">{post.title}</p>
          {fixReason ? (
            <p className="rounded-lg border border-red/35 bg-red/10 px-2.5 py-1.5 text-xs font-semibold leading-snug text-red">
              {fixReason}
            </p>
          ) : null}
          <p className="text-xs text-tx3">{factLine}</p>
          {channel ? <p className="text-xs font-medium text-tx2">{channel}</p> : null}
          {isCandidate && !isHoliday ? (
            <div className="pt-1">
              <button
                type="button"
                disabled={lodging || noDate}
                title={noDate ? 'Set a date on Inbox before lodging' : 'Lodge this candidate'}
                onClick={(e) => void handleLodge(e)}
                className="rounded-full bg-ac px-3 py-1 text-xs font-semibold text-bg disabled:opacity-40"
              >
                Lodge
              </button>
            </div>
          ) : null}
          {isScheduled ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                disabled={releasing}
                title="Release now — sandbox writes a receipt immediately"
                onClick={(e) => void handleRelease(e)}
                className="rounded-full bg-ac px-3 py-1 text-xs font-semibold text-bg disabled:opacity-40"
              >
                Release now
              </button>
              {post.inbox_item_id ? (
                <Link
                  to={`/review/${encodeURIComponent(String(post.inbox_item_id))}`}
                  className="text-xs font-semibold text-ac"
                  onClick={(e) => e.stopPropagation()}
                >
                  View draft
                </Link>
              ) : null}
            </div>
          ) : null}
          {isReleased ? (
            <p className="pt-1 text-xs font-medium text-tx2">
              Waiting to go out — the hourly job sends it at the scheduled time. Publish now is on the Publish page.
            </p>
          ) : null}
        </div>
      </div>
      {!isHoliday ? (
        <div className="w-full overflow-x-auto border-t border-white/5 pt-3">
          <StageStepper stages={post.stages} />
        </div>
      ) : null}
    </div>
  )

  const shell = `glass rounded-2xl border-[1.5px] px-3 py-3 backdrop-blur-xl md:px-4 ${
    isCandidate ? 'border-dashed border-white/10' : 'border-white/10'
  } ${isHoliday ? 'opacity-75' : ''}`

  if (!clickable) {
    return <li className={`${shell} ${isHoliday ? 'pointer-events-none' : 'opacity-90'}`}>{inner}</li>
  }
  return (
    <li>
      <Link to={to!} className={`block ${shell} transition hover:border-ac/50`}>
        {inner}
      </Link>
    </li>
  )
}
