import {
  Hash,
  Image,
  Laugh,
  Library,
  Megaphone,
  PenLine,
  Sparkles,
  Type,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../components/chrome'
import { Button, ClassicLink, IconTile, StatCard } from '../components/ui'
import { fetchToday, type TodayPanel } from '../lib/api'

const TOOLS: {
  id: string
  href?: string
  to?: string
  label: string
  hint: string
  icon: LucideIcon
  mode: string
}[] = [
  { id: 'post', to: '/create/post', label: 'Build a post', hint: 'Full draft in one pass', icon: Sparkles, mode: 'copy' },
  { id: 'captions', to: '/create/captions', label: 'Captions', hint: 'IG / FB / LinkedIn lengths', icon: Type, mode: 'copy' },
  { id: 'headlines', to: '/create/copy?tab=headlines', label: 'Headlines', hint: 'Punchy titles', icon: Megaphone, mode: 'copy' },
  { id: 'hooks', to: '/create/copy?tab=hooks', label: 'Hook bank', hint: 'Openers that stop scroll', icon: Hash, mode: 'copy' },
  { id: 'ctas', to: '/create/copy?tab=ctas', label: 'CTAs', hint: 'Ask for the click', icon: Megaphone, mode: 'copy' },
  { id: 'tags', to: '/create/copy?tab=hashtags', label: 'Hashtags', hint: 'Discoverability', icon: Hash, mode: 'copy' },
  { id: 'igen', to: '/create/images?tab=generate', label: 'Image gen', hint: 'Generate a still', icon: Image, mode: 'images' },
  { id: 'ilab', to: '/create/images?tab=lab', label: 'Image lab', hint: 'Iterate and crop', icon: Sparkles, mode: 'images' },
  { id: 'viz', to: '/create/images?tab=library', label: 'Visual library', hint: 'Past assets', icon: Library, mode: 'images' },
  { id: 'lord', to: '/create/memes?tab=lord', label: 'Meme Lord', hint: 'Classic meme desk', icon: Laugh, mode: 'memes' },
  { id: 'mlab', to: '/create/memes?tab=lab', label: 'Meme lab', hint: 'Templates and remix', icon: Sparkles, mode: 'memes' },
  { id: 'lib', to: '/create/copy?tab=library', label: 'Copy library', hint: 'Reuse what worked', icon: Type, mode: 'library' },
]

export function Create() {
  const { brandId } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)
  const [mode, setMode] = useState('all')

  useEffect(() => {
    fetchToday(brandId)
      .then(setData)
      .catch(() => setData(null))
  }, [brandId])

  const drafts = data?.counts?.draft ?? 0
  const shown = mode === 'all' ? TOOLS : TOOLS.filter((t) => t.mode === mode)

  return (
    <div className="space-y-6">
      <PageIntro icon={Sparkles} badge="Studio" here="/create" title="Make a draft">
        One studio. Copy, stills, and memes stay where they are — they open from here.
        <span className="mt-2 block">
          <ClassicLink href="/?page=buildpost" label="Build a post (classic)" />
        </span>
      </PageIntro>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          to="/review"
          icon={PenLine}
          label="Drafts"
          value={data ? drafts : '—'}
          hint="In studio, not reviewed"
          tone="gold"
        />
        <StatCard
          to="/review"
          icon={Sparkles}
          label="Waiting"
          value={data ? (data.counts?.review ?? 0) : '—'}
          hint="Already in inbox"
          tone="mute"
        />
        <StatCard
          to="/create/copy?tab=library"
          icon={Library}
          label="Library"
          value="Open"
          hint="Reuse a past winner"
          tone="mute"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(360px,1fr)]">
        <HeroPanel
          icon={Sparkles}
          kicker="Start here"
          title="Build a post"
          meta="Caption, visual, and hook in one pass — then it lands in Review."
        >
          <Button to="/create/post" icon={Sparkles} tip="Open the full post builder. The draft lands in Review.">
            Build a post
          </Button>
          <Button to="/create/captions" icon={Type} tone="ghost" tip="Open caption studio only — no visual yet.">
            Just a caption
          </Button>
        </HeroPanel>
        <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
          <h2 className="font-display text-xl font-semibold">How this desk works</h2>
          <ol className="mt-4 space-y-3 text-sm text-tx2">
            <li>
              <span className="font-semibold text-yel">1.</span> Draft in studio
            </li>
            <li>
              <span className="font-semibold text-yel">2.</span> Review approves — still not live
            </li>
            <li>
              <span className="font-semibold text-yel">3.</span> Calendar parks it, Publish ships it
            </li>
          </ol>
        </section>
      </div>

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">Tools</h2>
          <FilterChips
            value={mode}
            onChange={setMode}
            options={[
              { id: 'all', label: 'All' },
              { id: 'copy', label: 'Copy' },
              { id: 'images', label: 'Images' },
              { id: 'memes', label: 'Memes' },
              { id: 'library', label: 'Library' },
            ]}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((tool) => (
            <IconTile key={tool.id} to={tool.to} href={tool.href} icon={tool.icon} label={tool.label} hint={tool.hint} />
          ))}
        </div>
      </section>
    </div>
  )
}
