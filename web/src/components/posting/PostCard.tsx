import { ImageIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  formatGoesOut,
  linkForPostState,
  nextActionFromStages,
  postFlagLabel,
  postingChannelLabel,
  postingWeekThumbUrl,
  postStateLabel,
  postStateTone,
  type PostingWeekPost,
} from '../../lib/postingWeek'
import { StageStepper } from './StageStepper'

function PostCardThumb({ imageUrl, title }: { imageUrl?: string | null; title: string }) {
  const [broken, setBroken] = useState(false)
  const src = postingWeekThumbUrl(imageUrl)
  const showImage = Boolean(src) && !broken
  return (
    <div
      className={`relative h-14 w-14 shrink-0 overflow-hidden rounded-xl border md:h-[4.5rem] md:w-[4.5rem] ${
        showImage ? 'border-bd bg-bg-2' : 'border-dashed border-bd bg-bg-2/50'
      }`}
    >
      {showImage ? (
        <img
          src={src!}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-tx3" aria-hidden>
          <ImageIcon className="h-5 w-5" strokeWidth={1.75} />
        </span>
      )}
      <span className="sr-only">{title}</span>
    </div>
  )
}

export function PostCard({
  post,
  dayDate,
  weekday,
}: {
  post: PostingWeekPost
  dayDate: string
  weekday: string
}) {
  const isCandidate = post.state === 'candidate'
  const isHoliday = post.flags?.includes('holiday')
  const to = linkForPostState(post)
  const clickable = Boolean(to) && !isHoliday
  const channel = postingChannelLabel(post.primary_channel)
  const nextAction = post.next_action || nextActionFromStages(post.stages)
  const factLine = `${formatGoesOut(dayDate, weekday)} · ${nextAction}`
  const tone = postStateTone(post.state)
  const toneClass =
    tone === 'bad'
      ? 'border-red/40 text-red'
      : tone === 'warn'
        ? 'border-yel/40 text-yel'
        : tone === 'ok'
          ? 'border-green/40 text-green'
          : 'border-bd text-tx2'

  const inner = (
    <div className="flex gap-3 md:items-start md:gap-4">
      <PostCardThumb imageUrl={post.image_url} title={post.title} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
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
          {post.state === 'needs_fix' && post.needs_fix_reason ? (
            <span className="text-xs font-semibold text-red">{post.needs_fix_reason}</span>
          ) : null}
        </div>
        <div className="flex flex-col gap-0.5 md:flex-row md:items-start md:justify-between md:gap-3">
          <p className="truncate font-display text-base font-semibold leading-snug">{post.title}</p>
          {channel ? (
            <span className="shrink-0 text-xs font-medium text-tx2 md:text-right">{channel}</span>
          ) : null}
        </div>
        <p className="text-xs text-tx3">{factLine}</p>
        {!isHoliday ? <StageStepper stages={post.stages} /> : null}
      </div>
    </div>
  )

  const shell = `rounded-2xl border bg-bg-2/40 px-3 py-3 md:px-4 ${
    isCandidate ? 'border-dashed border-bd' : 'border-bd'
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
