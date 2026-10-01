import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { pageLabel, previousPath, readNavTrail } from '../lib/navHistory'

export function BackLink({
  fallback,
  className,
  children,
  hideIfNoHistory,
}: {
  fallback: string
  className?: string
  children?: ReactNode
  hideIfNoHistory?: boolean
}) {
  const navigate = useNavigate()
  const loc = useLocation()
  const current = loc.pathname + loc.search
  const prev = previousPath(readNavTrail(), current)
  if (!prev && hideIfNoHistory) return null

  const dest = prev ?? fallback
  const title = `Back to ${pageLabel(dest)}.`

  return (
    <Link
      to={dest}
      title={title}
      className={className}
      onClick={(event) => {
        if (!prev) return
        event.preventDefault()
        navigate(-1)
      }}
    >
      {children ?? 'Back'}
    </Link>
  )
}
