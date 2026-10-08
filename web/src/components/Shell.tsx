import { Link, Outlet, useLocation } from 'react-router-dom'
import { BrandProvider, BrandSwitch } from './BrandSwitch'
import { PressIcon, Tip } from './ui'
import { formatStamp } from '../lib/stamp'
import { RAIL, SETTINGS, sectionFor, type RailItem } from '../lib/nav'
import { TOOL_BY_SLUG, parentLabel } from '../lib/tools'

const RAIL_ON =
  'bg-yel/12 text-yel shadow-[inset_0_0_0_1.5px_rgba(251,191,36,.85)]'

function RailLink({ item, on }: { item: RailItem; on: boolean }) {
  const Icon = item.icon
  const tip = `Go to ${item.label}: ${item.hint}.`
  return (
    <Tip text={tip} block>
      <Link
        to={item.to}
        title={tip}
        aria-current={on ? 'page' : undefined}
        className={[
          'group flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition-colors duration-150',
          on ? RAIL_ON : 'text-tx2 hover:bg-white/5 hover:text-tx',
        ].join(' ')}
      >
        <span className="glass-pill grid shrink-0 place-items-center rounded-md p-1.5">
          <PressIcon icon={Icon} className="h-4 w-4" tone={on ? 'on' : 'mute'} />
        </span>
        <span className="min-w-0">
          <span className="block font-semibold">{item.label}</span>
          <span className={`block text-[13px] ${on ? 'text-yel/80' : 'text-tx3'}`}>{item.hint}</span>
        </span>
      </Link>
    </Tip>
  )
}

export function Shell() {
  const loc = useLocation()
  const toolSlug = loc.pathname.startsWith('/tool/') ? loc.pathname.split('/')[2] : ''
  const tool = toolSlug ? TOOL_BY_SLUG[toolSlug] : undefined
  // A classic tool belongs to the section it was opened from.
  const current = sectionFor(tool ? tool.from : loc.pathname)
  const isDesk = loc.pathname.startsWith('/desk') || loc.pathname.startsWith('/tool')

  return (
    <BrandProvider>
    <div className="min-h-dvh bg-transparent text-tx lg:grid lg:h-dvh lg:grid-cols-[272px_1fr] lg:overflow-hidden">
      <aside className="glass hidden border-r border-white/10 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:overflow-y-auto">
        <div className="flex items-center gap-3 px-5 pt-7 pb-5">
          <span
            aria-hidden
            className="grid h-10 w-10 place-items-center rounded-xl bg-bg shadow-[0_0_20px_rgba(251,191,36,.18)]"
          >
            <svg viewBox="0 0 32 32" className="h-7 w-7" fill="none">
              <rect width="32" height="32" rx="6" fill="#0a0f1a" />
              <path d="M10 26V6" stroke="#fbbf24" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M10 8L22 11L10 14Z" fill="#fbbf24" />
              <circle cx="10" cy="27" r="1.5" fill="#34d399" />
            </svg>
          </span>
          <div>
            <p className="font-display text-lg font-semibold tracking-tight text-tx">
              Campaign OS
            </p>
            <p className="text-[13px] text-tx3">Plan · create · publish · learn</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3" aria-label="Campaigner rail">
          {RAIL.map((item) => (
            <RailLink key={item.to} item={item} on={item === current} />
          ))}
        </nav>
        <div className="border-t border-white/10 px-3 py-3">
          <RailLink item={SETTINGS} on={SETTINGS === current} />
        </div>
      </aside>

      <div className="flex min-h-dvh flex-col pb-20 lg:h-dvh lg:min-h-0 lg:overflow-visible lg:pb-0">
        <header className="glass sticky top-0 z-30 flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3 md:px-6">
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-bg lg:hidden">
              <svg viewBox="0 0 32 32" className="h-6 w-6" fill="none">
                <path d="M10 26V6" stroke="#fbbf24" strokeWidth="2.5" strokeLinecap="round" />
                <path d="M10 8L22 11L10 14Z" fill="#fbbf24" />
                <circle cx="10" cy="27" r="1.5" fill="#34d399" />
              </svg>
            </span>
            <div>
              <p className="font-display text-base font-semibold lg:hidden">Campaign OS</p>
              <p className="hidden text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase lg:block">
                {tool
                  ? `${parentLabel(tool.from)} · ${tool.label}`
                  : `${current?.label || 'Tool'} · ${current?.hint || 'inside the desk'}`}
              </p>
              <p className="text-[13px] text-tx3">{formatStamp()}</p>
            </div>
          </div>
          <BrandSwitch variant="bar" />
        </header>
        <main
          className={
            isDesk
              ? 'flex min-h-0 flex-1 flex-col overflow-hidden'
              : 'mx-auto w-full max-w-[1680px] min-h-0 flex-1 overflow-y-auto px-5 py-5 md:px-8 md:py-8'
          }
        >
          <Outlet />
        </main>
      </div>

      <nav
        className="glass fixed inset-x-0 bottom-0 z-20 grid grid-cols-6 border-t border-white/10 lg:hidden"
        aria-label="Campaigner rail"
      >
        {[...RAIL, SETTINGS].map((item) => {
          const Icon = item.icon
          const on = item === current
          return (
            <Link
              key={item.to}
              to={item.to}
              title={`Go to ${item.label}: ${item.hint}.`}
              aria-current={on ? 'page' : undefined}
              className={[
                'flex min-h-14 flex-col items-center justify-center gap-0.5 px-0.5 text-center text-[12px] font-medium leading-tight',
                on ? RAIL_ON : 'text-tx3',
              ].join(' ')}
            >
              <PressIcon icon={Icon} className="h-4 w-4" tone={on ? 'on' : 'mute'} />
              {item.label}
            </Link>
          )
        })}
      </nav>
    </div>
    </BrandProvider>
  )
}
