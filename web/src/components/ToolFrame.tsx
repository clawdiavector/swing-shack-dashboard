import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Tip } from './ui'

export function ToolFrame({
  back,
  backLabel,
  title,
  hint,
  chip,
  src,
}: {
  back: string
  backLabel: string
  title: string
  hint?: string
  chip?: string
  src: string
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-white/10 px-4 py-3 md:px-6">
        <Tip text={`Go back to ${backLabel}.`}>
        <Link
          to={back}
          title={`Go back to ${backLabel}.`}
          className="glass-pill inline-flex items-center gap-1.5 rounded-full border border-white/10 px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={2.5} />
          {backLabel}
        </Link>
        </Tip>
        <div className="min-w-0">
          <p className="font-display text-lg font-semibold leading-tight">{title}</p>
          {hint ? <p className="text-[13px] text-tx3">{hint}</p> : null}
        </div>
        {chip ? (
          <span className="ml-auto max-w-md truncate rounded-full bg-yel/15 px-3 py-1 text-xs font-semibold text-yel">
            {chip}
          </span>
        ) : null}
      </div>
      <iframe title={title} src={src} className="block min-h-0 w-full flex-1 border-0 bg-bg" />
    </div>
  )
}
