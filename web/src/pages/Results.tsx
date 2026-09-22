import { Activity, BookOpen, LineChart, Search, Sparkles, TrendingUp } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useBrand } from '../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../components/chrome'
import { Button, IconTile, StatCard } from '../components/ui'
import { fetchToday, type TodayPanel } from '../lib/api'

const TABS: { href: string; label: string; hint: string; icon: LucideIcon }[] = [
  { href: '/results/week', label: 'This week', hint: 'Weekly report', icon: LineChart },
  { href: '/results/worked?tab=posts', label: 'What worked', hint: 'Insights', icon: Sparkles },
  { href: '/?page=performance', label: 'Reach', hint: 'Performance', icon: Activity },
  { href: '/results/worked?tab=recipes', label: 'Learnings', hint: 'Recipes', icon: BookOpen },
  { href: '/?page=trends', label: 'Trends', hint: 'What is moving', icon: TrendingUp },
  { href: '/?page=seo', label: 'SEO', hint: 'Rankings and audit', icon: Search },
]

export function Results() {
  const { brandId, brandLabel } = useBrand()
  const [data, setData] = useState<TodayPanel | null>(null)

  useEffect(() => {
    fetchToday(brandId)
      .then(setData)
      .catch(() => setData(null))
  }, [brandId])

  const published = data?.counts?.published ?? 0
  const brand = brandLabel || data?.active_brand_label || data?.active_brand_id || 'this brand'

  return (
    <div className="space-y-6">
      <PageIntro icon={Activity} badge="What worked" here="/results" title="Results">
        Reports and outcomes for {brand}. Daily already shows the headline numbers.
      </PageIntro>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          icon={Sparkles}
          label="Shipped"
          value={data ? published : '—'}
          hint="This week’s live posts"
          tone="green"
        />
        <StatCard
          to="/results/week"
          icon={LineChart}
          label="Weekly"
          value="Open"
          hint="Full weekly report"
          tone="gold"
        />
        <StatCard
          href="/?page=seo"
          icon={Search}
          label="SEO"
          value="Audit"
          hint="Rankings and gaps"
          tone="mute"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(380px,1fr)]">
        <HeroPanel
          icon={LineChart}
          kicker="Read this first"
          title="This week’s report"
          meta="What shipped, what moved, and what to do next Monday."
        >
          <Button to="/results/week" icon={LineChart} tip="Open this week’s full report.">
            Open weekly report
          </Button>
          <Button to="/results/worked?tab=posts" icon={Sparkles} tone="ghost" tip="Open what worked — posts, reach, and recipes.">
            Insights
          </Button>
        </HeroPanel>
        <section className="glass rounded-2xl border-[1.5px] border-white/10 p-5 backdrop-blur-xl">
          <h2 className="font-display text-xl font-semibold">How to read it</h2>
          <ul className="mt-4 space-y-3 text-sm text-tx2">
            <li>
              <span className="font-semibold text-ac">Reach</span> — did anyone see it
            </li>
            <li>
              <span className="font-semibold text-yel">What worked</span> — repeat the winner
            </li>
            <li>
              <span className="font-semibold text-tx">Learnings</span> — write it down so next week is easier
            </li>
          </ul>
        </section>
      </div>

      <section>
        <h2 className="mb-3 font-display text-xl font-semibold">All reports</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {TABS.map((tab) => (
            <IconTile key={tab.href} href={tab.href} icon={tab.icon} label={tab.label} hint={tab.hint} />
          ))}
        </div>
      </section>
    </div>
  )
}
