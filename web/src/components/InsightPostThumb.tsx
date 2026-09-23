import { useState } from 'react'
import { fetchSocialsOembed, type InsightPost } from '../lib/api'

export function insightPostThumbSrc(post: InsightPost): string {
  if (post.thumbnail_url) return post.thumbnail_url
  if ((post.media_type || '').toUpperCase() === 'VIDEO') return post.oembed_thumbnail || ''
  if (post.media_url) return post.media_url
  return post.oembed_thumbnail || ''
}

type InsightPostThumbProps = {
  post: InsightPost
  thumbKey: string
  className?: string
  placeholderClassName?: string
}

export function InsightPostThumb({
  post,
  thumbKey,
  className = 'h-16 w-16 rounded-xl object-cover',
  placeholderClassName: _placeholderClassName = 'grid h-16 w-16 place-items-center rounded-xl text-[12px] text-tx3',
}: InsightPostThumbProps) {
  void _placeholderClassName
  const [brokenPrimary, setBrokenPrimary] = useState(false)
  const [oembedThumb, setOembedThumb] = useState('')
  const [oembedTried, setOembedTried] = useState(false)

  const primary = insightPostThumbSrc(post)
  const src = oembedThumb || (primary && !brokenPrimary ? primary : '')

  async function handleError() {
    if (oembedTried || !post.permalink) {
      setBrokenPrimary(true)
      return
    }
    setOembedTried(true)
    setBrokenPrimary(true)
    try {
      const res = await fetchSocialsOembed(post.permalink)
      if (res.ok && res.thumbnail_url) {
        setOembedThumb(res.thumbnail_url)
      }
    } catch {
      /* keep placeholder */
    }
  }

  if (src) {
    return (
      <img
        key={thumbKey}
        src={src}
        alt=""
        loading="lazy"
        onError={() => {
          void handleError()
        }}
        className={className}
      />
    )
  }

  return null
}
