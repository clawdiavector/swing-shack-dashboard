import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { RAIL } from '../lib/nav'
import { Badge, Button, PressIcon, Tip } from './ui'

export function RailStrip({ here }: { here: string }) {
  return (
    <div className="glass-pill hidden items-center gap-1 rounded-full border border-white/10 p-1 md:flex">
      {RAIL.slice(0, 5).map((step) => {
        const Icon = step.icon
        const on = step.to === here
        const tip = `Go to ${step.label}: ${step.hint}.`
        return (
          <Tip key={step.to} text={tip}>
          <Link
            to={step.to}
            title={tip}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${
              on ? 'bg-yel/15 text-yel' : 'text-tx3 hover:text-tx'
            }`}
          >
            <PressIcon icon={Icon} className="h-4 w-4" tone={on ? 'on' : 'mute'} />
            {step.label}
          </Link>
          </Tip>
        )
      })}
    </div>
  )
}

export function PageIntro({
  title,
  children,
  here,
  actions,
}: {
  icon?: LucideIcon
  badge?: string
  title: ReactNode
  children?: ReactNode
  here: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <header>
        <h1 className="font-display text-[36px] leading-[1.1] font-semibold md:text-5xl">{title}</h1>
        {children ? <p className="mt-2 max-w-4xl text-sm text-tx2 md:text-base">{children}</p> : null}
      </header>
      <div className="flex flex-col items-end gap-3">
        <RailStrip here={here} />
        {actions}
      </div>
    </div>
  )
}

export function HeroPanel({
  icon: Icon,
  kicker,
  title,
  meta,
  children,
  extra,
}: {
  icon: LucideIcon
  kicker: string
  title: string
  meta?: string
  children?: ReactNode
  extra?: ReactNode
}) {
  return (
    <section className="glass relative flex h-full flex-col overflow-visible rounded-2xl border-[1.5px] border-ac/35 p-5 shadow-[0_0_0_3px_rgba(52,211,153,.08)] backdrop-blur-xl">
      <div className="pointer-events-none absolute -top-16 -right-10 h-40 w-40 rounded-full bg-yel/8 blur-3xl" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="glass-pill grid place-items-center rounded-xl p-2.5">
            <PressIcon icon={Icon} className="h-8 w-8" tone="green" />
          </span>
          <h2 className="font-display text-xl font-semibold">{kicker}</h2>
        </div>
        <Badge tone="green">Focus</Badge>
      </div>
      <p className="mt-4 font-display text-2xl leading-snug font-medium md:text-3xl">{title}</p>
      {meta ? <p className="mt-2 text-sm text-tx3">{meta}</p> : null}
      {children ? <div className="mt-5 flex flex-wrap gap-2">{children}</div> : null}
      {extra ? <div className="mt-5 min-h-0 flex-1">{extra}</div> : null}
    </section>
  )
}

export function FilterChips({
  value,
  options,
  onChange,
}: {
  value: string
  options: { id: string; label: string }[]
  onChange: (id: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((opt) => (
        <Tip key={opt.id} text={opt.id === 'all' ? 'Show every item in this list.' : `Show only ${opt.label}.`}>
        <button
          type="button"
          title={opt.id === 'all' ? 'Show every item in this list.' : `Show only ${opt.label}.`}
          onClick={() => onChange(opt.id)}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
            value === opt.id ? 'bg-yel/15 text-yel' : 'glass-pill text-tx3 hover:text-tx'
          }`}
        >
          {opt.label}
        </button>
        </Tip>
      ))}
    </div>
  )
}

export function MonthGrid({
  highlight,
  embedded,
  counts,
  selected,
  onSelect,
}: {
  highlight?: number
  embedded?: boolean
  counts?: Record<number, number>
  selected?: number | null
  onSelect?: (day: number) => void
}) {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth()
  const today = now.getDate()
  const first = new Date(year, month, 1)
  const pad = (first.getDay() + 6) % 7
  const days = new Date(year, month + 1, 0).getDate()
  const cells = [...Array(pad).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)]
  while (cells.length % 7) cells.push(null)
  const monthName = now.toLocaleString('en-ZA', { month: 'long' })

  return (
    <div className={embedded ? 'pt-1' : 'glass rounded-2xl border-[1.5px] border-white/10 p-4 backdrop-blur-xl'}>
      <div className="mb-3 grid grid-cols-7 text-center text-[12px] font-semibold tracking-wide text-tx3 uppercase">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((day, i) => {
          if (!day) return <span key={`e-${i}`} className="aspect-square" />
          const n = counts?.[day] ?? 0
          const isToday = day === today
          const isOn = day === selected || (!selected && day === highlight)
          const tip =
            n > 0
              ? `${n} parked on ${day} ${monthName}. Show what’s on this day.`
              : `Nothing parked on ${day} ${monthName}. Open this day to park a draft.`
          return (
            <Tip key={day} text={tip} block>
              <button
                type="button"
                title={tip}
                onClick={() => onSelect?.(day)}
                className={`relative grid aspect-square w-full place-items-center rounded-lg text-sm ${
                  isOn
                    ? 'bg-yel/20 font-semibold text-yel'
                    : isToday
                      ? 'bg-ac/15 font-semibold text-ac'
                      : n
                        ? 'text-tx hover:bg-white/8'
                        : 'text-tx2 hover:bg-white/8'
                }`}
              >
                {day}
                {n ? (
                  <span className="absolute bottom-1 h-1.5 w-1.5 rounded-full bg-ac" aria-hidden />
                ) : null}
              </button>
            </Tip>
          )
        })}
      </div>
    </div>
  )
}

export { Button }
