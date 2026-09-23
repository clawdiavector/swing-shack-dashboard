import type { LucideIcon } from 'lucide-react'
import { ExternalLink } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { toDesk } from '../lib/desk'
import { formatDateStamp, formatStamp, stampLabel } from '../lib/stamp'

export function PressIcon({
  icon: Icon,
  className = 'h-6 w-6',
  tone = 'mute',
}: {
  icon: LucideIcon
  className?: string
  tone?: 'mute' | 'gold' | 'green' | 'on'
}) {
  return (
    <span className={`icon-press icon-press-${tone} ${className}`} aria-hidden>
      <Icon className="icon-press-shade size-full" strokeWidth={2.5} />
      <Icon className="icon-press-hi size-full" strokeWidth={2.5} />
      <Icon className="icon-press-ink size-full" strokeWidth={2.5} />
    </span>
  )
}

export function Badge({
  tone = 'mute',
  children,
}: {
  tone?: 'mute' | 'gold' | 'green' | 'blue' | 'red'
  children: ReactNode
}) {
  const tones = {
    mute: 'glass-pill text-tx2',
    gold: 'bg-yel/15 text-yel',
    green: 'bg-ac/15 text-ac',
    blue: 'bg-blu/15 text-blu',
    red: 'bg-red/15 text-red',
  }
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold tracking-wide uppercase ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

export function Tip({
  text,
  block,
  children,
}: {
  text: string
  block?: boolean
  children: ReactNode
}) {
  return (
    <span className={block ? 'cos-tip cos-tip-block' : 'cos-tip'}>
      {children}
      <span className="cos-tip-bubble" role="tooltip">
        {text}
      </span>
    </span>
  )
}

export function ClassicLink({
  href,
  label,
  tip: tipProp,
}: {
  href: string
  label: string
  /** Custom bubble text, or `false` to render a plain link (no Tip). */
  tip?: string | false
}) {
  const defaultTip = `Open the classic ${label} page in a full tab. Leftover HTML stays live.`
  const link = (
    <a
      href={href}
      className="inline-flex items-center gap-1 text-sm font-semibold text-ac hover:text-yel"
    >
      Open in Classic
      <ExternalLink className="h-3.5 w-3.5" strokeWidth={2.5} />
    </a>
  )
  if (tipProp === false) return link
  const tipText = tipProp ?? defaultTip
  return <Tip text={tipText}>{link}</Tip>
}

export function Button({
  to,
  href,
  icon: Icon,
  tone = 'gold',
  tip,
  children,
}: {
  to?: string
  href?: string
  icon?: LucideIcon
  tone?: 'gold' | 'ghost' | 'green'
  tip: string
  children: ReactNode
}) {
  const cls = [
    'inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition-colors duration-150',
    tone === 'gold' && 'bg-yel text-bg hover:bg-yel/90',
    tone === 'green' && 'bg-ac text-bg hover:bg-ac/90',
    tone === 'ghost' && 'glass-pill border border-white/10 text-tx hover:border-ac hover:text-ac',
  ]
    .filter(Boolean)
    .join(' ')
  const inner = (
    <>
      {Icon ? (
        tone === 'ghost' ? (
          <PressIcon icon={Icon} className="h-4 w-4" />
        ) : (
          <Icon className="h-4 w-4" strokeWidth={2.5} />
        )
      ) : null}
      {children}
    </>
  )
  return (
    <Tip text={tip}>
      <Link to={to || toDesk(href || '/daily')} className={cls}>
        {inner}
      </Link>
    </Tip>
  )
}

export function StatCard({
  to,
  href,
  icon: Icon,
  label,
  value,
  hint,
  tone = 'mute',
  stamp,
  stampKind,
}: {
  to?: string
  href?: string
  icon: LucideIcon
  label: string
  value: string | number
  hint: string
  tone?: 'gold' | 'green' | 'mute'
  stamp?: string | null
  stampKind?: string
}) {
  const ring =
    tone === 'gold'
      ? 'border-yel/30 shadow-[0_0_24px_rgba(251,191,36,.1)]'
      : tone === 'green'
        ? 'border-ac/25'
        : 'border-bd'
  const valueCls = tone === 'gold' ? 'text-yel' : tone === 'green' ? 'text-ac' : 'text-tx'
  const body = (
    <>
      <div className="flex items-start justify-between">
        <p className="text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase">{label}</p>
        <span className="glass-pill grid place-items-center rounded-xl p-2.5">
          <PressIcon
            icon={Icon}
            className="h-8 w-8"
            tone={tone === 'gold' ? 'gold' : tone === 'green' ? 'green' : 'mute'}
          />
        </span>
      </div>
      <p className={`mt-1 font-display text-3xl font-semibold ${valueCls}`}>{value}</p>
      <p className="mt-0.5 text-xs text-tx3">{hint}</p>
      {stamp ? (
        <p className="mt-0.5 text-[12px] font-semibold tracking-wide text-tx3 uppercase">
          {stampLabel(stampKind)} {formatStamp(stamp)}
        </p>
      ) : null}
    </>
  )
  const cls = `glass block rounded-2xl border-[1.5px] px-3 py-3 backdrop-blur-xl ${ring}`
  const tip = to || href ? `Opens ${label}. ${hint}` : hint
  if (to || href) {
    return (
      <Tip text={tip} block>
        <Link to={to || toDesk(href || '/daily')} className={cls}>
          {body}
        </Link>
      </Tip>
    )
  }
  return <div className={cls}>{body}</div>
}

export function IconTile({
  href,
  to,
  icon: Icon,
  label,
  hint,
}: {
  href?: string
  to?: string
  icon: LucideIcon
  label: string
  hint?: string
}) {
  const tip = hint ? `Opens ${label}. ${hint}` : `Opens ${label}.`
  const dest = to || toDesk(href || '/daily')
  return (
    <Tip text={tip} block>
    <Link
      to={dest}
      className="glass group flex items-start gap-2 rounded-2xl border-[1.5px] border-white/10 p-4 backdrop-blur-xl hover:border-ac/40"
    >
      <span className="glass-pill grid shrink-0 place-items-center rounded-xl p-2.5">
        <PressIcon icon={Icon} className="h-8 w-8" tone="gold" />
      </span>
      <span>
        <span className="block text-sm font-semibold">{label}</span>
        {hint ? <span className="mt-0.5 block text-xs text-tx3">{hint}</span> : null}
      </span>
    </Link>
    </Tip>
  )
}

export function PageHeader({
  kicker,
  title,
  children,
}: {
  kicker: string
  title: string
  children?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-[13px] font-semibold tracking-[0.16em] text-tx3 uppercase">{kicker}</p>
        <h1 className="mt-1 font-display text-[32px] leading-tight font-semibold md:text-4xl">
          {title}
        </h1>
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </header>
  )
}

function QueueItemThumb({ src, alt }: { src: string; alt: string }) {
  const [hidden, setHidden] = useState(false)
  if (hidden) return null
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setHidden(true)}
      className="h-12 w-12 shrink-0 rounded-xl border border-bd object-cover"
    />
  )
}

export function QueueItem({
  to,
  tip: tipText,
  badge,
  tone,
  channelBadge,
  channelTone,
  title,
  meta,
  stamp,
  stampKind,
  dateOnly,
  action,
  footer,
  thumb,
  thumbAlt,
}: {
  to?: string
  tip?: string
  badge: string
  tone: 'gold' | 'green' | 'blue' | 'mute'
  channelBadge?: string
  channelTone?: 'gold' | 'green' | 'blue' | 'mute'
  title: string
  meta?: string
  stamp?: string | null
  stampKind?: string
  dateOnly?: boolean
  action?: ReactNode
  footer?: ReactNode
  thumb?: string
  thumbAlt?: string
}) {
  const when = dateOnly ? formatDateStamp(stamp) : formatStamp(stamp)
  const thumbNode = thumb ? <QueueItemThumb src={thumb} alt={thumbAlt || title} /> : null
  const body = (
    <>
      {thumbNode}
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={tone}>{badge}</Badge>
          {channelBadge ? (
            <Badge tone={channelTone || 'blue'}>{channelBadge}</Badge>
          ) : null}
          <span className="text-[12px] font-semibold tracking-wide text-tx3 uppercase">
            {stampLabel(stampKind)} {when}
          </span>
        </div>
        <p className="mt-1.5 text-sm leading-snug font-medium">{title}</p>
        {meta ? <p className="mt-0.5 text-xs text-tx3">{meta}</p> : null}
      </div>
      {action}
    </>
  )
  const cls =
    'glass flex items-start justify-between gap-3 rounded-2xl border-[1.5px] border-white/10 px-4 py-3 backdrop-blur-xl'
  const tip = to ? tipText || 'Open this piece.' : undefined
  return (
    <li>
      {to ? (
        <Tip text={tip as string} block>
          <Link to={to} title={tip} className={`${cls} hover:border-ac/40`}>
            {body}
          </Link>
        </Tip>
      ) : (
        <div className={cls}>{body}</div>
      )}
      {footer ? <div className="mt-1">{footer}</div> : null}
    </li>
  )
}
