import { MoreHorizontal, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { PageIntro } from '../components/chrome'
import { IconTile, PressIcon } from '../components/ui'
import { OTHER_GROUPS } from '../lib/nav'

export function Other() {
  const [q, setQ] = useState('')
  const query = q.trim().toLowerCase()

  const groups = useMemo(() => {
    if (!query) return OTHER_GROUPS
    return OTHER_GROUPS.map((group) => ({
      ...group,
      items: group.items.filter((item) => item.label.toLowerCase().includes(query)),
    })).filter((group) => group.items.length)
  }, [query])

  return (
    <div className="space-y-6">
      <PageIntro icon={MoreHorizontal} badge="Leftovers" here="/other" title="Other">
        Nothing here is deleted. Review later and say what dies. Jobs and agents moved to Ops on the rail.
      </PageIntro>

      <label className="glass flex items-center gap-3 rounded-2xl border-[1.5px] border-white/10 px-4 py-3 backdrop-blur-xl">
        <PressIcon icon={Search} className="h-4 w-4" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search leftover tools…"
          className="w-full bg-transparent text-sm outline-none placeholder:text-tx3"
        />
      </label>

      {groups.map((group) => {
        const Icon = group.icon
        return (
          <section key={group.title}>
            <div className="mb-3 flex items-center gap-1.5">
              <span className="glass-pill grid place-items-center rounded-xl p-2.5">
                <PressIcon icon={Icon} className="h-8 w-8" tone="gold" />
              </span>
              <h2 className="font-display text-xl font-semibold">{group.title}</h2>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {group.items.map((item) => (
                <IconTile key={item.href} href={item.href} icon={item.icon} label={item.label} />
              ))}
            </div>
          </section>
        )
      })}
      {groups.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-8 text-sm text-tx3">
          Nothing matches that search.
        </p>
      ) : null}
    </div>
  )
}
