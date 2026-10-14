import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { toDesk } from '../lib/desk'
import { formatStamp, stampLabel } from '../lib/stamp'
import type { PostingWeekDay } from '../lib/postingWeek'
import { Tip } from './ui'

export type FunTone = 'gold' | 'green' | 'blue' | 'violet'

/** Friendly blob that lives in the corner of Today. Colour follows the tone. */
export function Mascot({ tone = 'gold', className = '' }: { tone?: FunTone; className?: string }) {
  const fill = {
    gold: 'var(--play-gold, var(--color-yel))',
    green: 'var(--play-green, var(--color-ac))',
    blue: 'var(--play-blue, var(--color-blu))',
    violet: 'var(--play-violet, var(--color-lane-paid))',
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

/** The link-eating chomper. `state` drives the lid and wiggle in fun.css. */
export function Chomper({ state = 'idle' }: { state?: 'idle' | 'hungry' | 'munch' | 'nope' }) {
  return (
    <svg className="fun-chomper" data-state={state} viewBox="0 0 120 120" aria-hidden>
      <path d="M14 66c0-32 20-52 46-52s46 20 46 52v34c0 8-6 14-14 14H28c-8 0-14-6-14-14z" fill="var(--play-blue, var(--color-blu))" />
      <g className="fun-chomper__lid">
        <path d="M14 66c0-32 20-52 46-52s46 20 46 52z" fill="var(--play-green, var(--color-ac))" />
      </g>
      <g className="fun-eye">
        <circle cx="42" cy="46" r="9" fill="#fff" />
        <circle cx="44" cy="48" r="4" fill="#1b1a22" />
      </g>
      <g className="fun-eye">
        <circle cx="78" cy="46" r="9" fill="#fff" />
        <circle cx="80" cy="48" r="4" fill="#1b1a22" />
      </g>
      <path
        className="fun-chomper__mouth"
        d="M36 82c14 12 34 12 48 0"
        stroke="#2a1c66"
        strokeWidth="6"
        fill="none"
        strokeLinecap="round"
      />
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

/** Seven day pills across the top of This week: how full each day is, tap to open it. */
export function WeekStrip({
  days,
  onPick,
}: {
  days: PostingWeekDay[]
  onPick: (dateIso: string) => void
}) {
  return (
    <div className="fun-strip" role="list" aria-label="The week at a glance">
      {days.map((day) => {
        const n = day.posts.length
        const tone: FunTone = n === 0 ? 'blue' : n >= 3 ? 'green' : 'gold'
        const dd = Number(day.date.slice(8, 10))
        return (
          <button
            key={day.date}
            type="button"
            role="listitem"
            className="fun-day-pill"
            data-tone={tone}
            data-today={day.is_today ? 'true' : undefined}
            data-empty={n === 0 ? 'true' : undefined}
            onClick={() => onPick(day.date)}
            title={n === 0 ? `Nothing going out on ${day.weekday}. Open the day.` : `${n} going out on ${day.weekday}. Open the day.`}
          >
            <span className="fun-day-pill__wd">{day.weekday.slice(0, 3)}</span>
            <span className="fun-day-pill__dd">{dd}</span>
            <span className="fun-dots" aria-hidden>
              {[0, 1, 2].map((i) => (
                <i key={i} data-on={i < n} />
              ))}
            </span>
            <span className="fun-day-pill__n">{n === 0 ? 'open' : `${n} post${n === 1 ? '' : 's'}`}</span>
          </button>
        )
      })}
    </div>
  )
}
