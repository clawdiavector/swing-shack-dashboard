import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { toDesk } from '../lib/desk'
import { formatStamp, stampLabel } from '../lib/stamp'
import { Tip } from './ui'

export type FunTone = 'gold' | 'green' | 'blue' | 'violet'

/** Friendly blob that lives in the corner of Today. Colour follows the tone. */
export function Mascot({ tone = 'gold', className = '' }: { tone?: FunTone; className?: string }) {
  const fill = {
    gold: 'var(--color-yel)',
    green: 'var(--color-ac)',
    blue: 'var(--color-blu)',
    violet: 'var(--color-lane-paid)',
  }[tone]
  return (
    <svg className={`fun-mascot ${className}`} viewBox="0 0 120 120" aria-hidden>
      <path
        d="M60 8c26 0 50 18 51 46 1 30-17 58-51 58S9 84 10 54C11 26 34 8 60 8z"
        fill={fill}
      />
      <path d="M24 34c-9-6-6-18 4-21 5 9 4 16-4 21zM96 34c9-6 6-18-4-21-5 9-4 16 4 21z" fill={fill} />
      <g className="fun-eye">
        <circle cx="43" cy="55" r="9" fill="#fff" />
        <circle cx="46" cy="57" r="4" fill="#0a0f1a" />
      </g>
      <g className="fun-eye">
        <circle cx="77" cy="55" r="9" fill="#fff" />
        <circle cx="80" cy="57" r="4" fill="#0a0f1a" />
      </g>
      <path d="M44 78c9 11 23 11 32 0" stroke="#0a0f1a" strokeWidth="5" fill="none" strokeLinecap="round" />
      <circle cx="29" cy="72" r="6" fill="#f87171" opacity=".45" />
      <circle cx="91" cy="72" r="6" fill="#f87171" opacity=".45" />
    </svg>
  )
}

/** Share of the desk that is ready to ship versus still waiting on a call. */
export function DeskRing({ ready, waiting }: { ready: number; waiting: number }) {
  const total = ready + waiting
  const pct = total === 0 ? 100 : Math.round((ready / total) * 100)
  const C = 2 * Math.PI * 34
  return (
    <svg
      className="fun-ring"
      viewBox="0 0 80 80"
      role="img"
      aria-label={`${pct}% of the desk is ready to ship`}
    >
      <circle cx="40" cy="40" r="34" fill="none" stroke="var(--color-bd)" strokeWidth="9" />
      <circle
        className="fun-ring__arc"
        cx="40"
        cy="40"
        r="34"
        fill="none"
        stroke="var(--color-ac)"
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={C}
        strokeDashoffset={C - (C * pct) / 100}
        transform="rotate(-90 40 40)"
      />
      <text
        x="40"
        y="46"
        textAnchor="middle"
        fontSize="19"
        fontWeight="700"
        fill="var(--color-tx)"
        style={{ fontFamily: 'var(--font-display)' }}
      >
        {pct}%
      </text>
    </svg>
  )
}

/** Chunky stat tile. Same job as StatCard: a number, what it counts, where it goes. */
export function FunTile({
  to,
  href,
  label,
  value,
  hint,
  tone = 'green',
  stamp,
  stampKind,
  dots,
}: {
  to?: string
  href?: string
  label: string
  value: string | number
  hint: string
  tone?: FunTone
  stamp?: string | null
  stampKind?: string
  /** Up to 7 dots; the first `on` are lit. Omit for no dots. */
  dots?: { on: number; of?: number }
}) {
  const of = dots?.of ?? 7
  const body: ReactNode = (
    <>
      <p className="fun-tile__label">{label}</p>
      <p className="fun-tile__value">{value}</p>
      <p className="fun-tile__hint">{hint}</p>
      {dots ? (
        <div className="fun-dots" aria-hidden>
          {Array.from({ length: of }, (_, i) => (
            <i key={i} data-on={i < dots.on} />
          ))}
        </div>
      ) : null}
      {stamp ? (
        <p className="fun-tile__stamp">
          {stampLabel(stampKind, stamp)} {formatStamp(stamp)}
        </p>
      ) : null}
    </>
  )
  if (to || href) {
    return (
      <Tip text={`Opens ${label}. ${hint}`} block>
        <Link to={to || toDesk(href || '/daily')} className="fun-tile" data-tone={tone}>
          {body}
        </Link>
      </Tip>
    )
  }
  return (
    <div className="fun-tile" data-tone={tone}>
      {body}
    </div>
  )
}
