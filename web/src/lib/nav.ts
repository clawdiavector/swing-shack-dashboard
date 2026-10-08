import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Bot,
  Building2,
  CalendarDays,
  ClipboardCheck,
  FileStack,
  Flag,
  FolderKanban,
  Inbox,
  Layers,
  LayoutDashboard,
  MoreHorizontal,
  Palette,
  Rocket,
  Settings,
  Sparkles,
  Sun,
} from 'lucide-react'

export type RailItem = {
  to: string
  label: string
  hint: string
  icon: LucideIcon
  /** Route prefixes that belong to this section. */
  match: string[]
  /** The section's pages, shown as tabs at the top of each one. */
  pages: { to: string; label: string }[]
}

// Five places in the order the work happens. Pages that used to have their
// own rail item (Inbox, Review, This week, Shelf) are tabs inside the
// section they belong to, so each is still one click from its section.
export const RAIL: RailItem[] = [
  {
    to: '/daily',
    label: 'Today',
    hint: 'What needs you',
    icon: Sun,
    match: ['/daily', '/review', '/inbox'],
    pages: [
      { to: '/daily', label: 'Today' },
      { to: '/review', label: 'Approve drafts' },
      { to: '/inbox', label: 'Inbox' },
    ],
  },
  {
    to: '/calendar/lanes',
    label: 'Plan',
    hint: 'Calendar',
    icon: CalendarDays,
    match: ['/calendar', '/week'],
    pages: [
      { to: '/calendar/lanes', label: 'Plan' },
      { to: '/week', label: 'This week' },
    ],
  },
  {
    to: '/create',
    label: 'Create',
    hint: 'Posts, captions, images',
    icon: Sparkles,
    match: ['/create'],
    pages: [{ to: '/create', label: 'Create' }],
  },
  {
    to: '/publish',
    label: 'Publish',
    hint: 'Scheduled and going live',
    icon: Rocket,
    match: ['/publish', '/shelf'],
    pages: [
      { to: '/publish', label: 'Publish' },
      { to: '/shelf', label: 'Scheduled' },
    ],
  },
  {
    to: '/results',
    label: 'Results',
    hint: 'What worked',
    icon: Activity,
    match: ['/results'],
    pages: [{ to: '/results', label: 'Results' }],
  },
]

/** Sits apart at the foot of the rail: everything that is not the daily work. */
export const SETTINGS: RailItem = {
  to: '/ops',
  label: 'Settings',
  hint: 'Ops, brand, accounts',
  icon: Settings,
  match: ['/ops', '/other', '/brand', '/library', '/geo', '/desk'],
  pages: [
    { to: '/ops', label: 'Ops' },
    { to: '/other', label: 'Everything else' },
  ],
}

function under(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`)
}

/** The section a route belongs to. */
export function sectionFor(path: string): RailItem | undefined {
  return [...RAIL, SETTINGS].find((item) => item.match.some((prefix) => under(path, prefix)))
}

/** Which of a section's tabs a route is on (the longest matching one), if any. */
export function sectionPageFor(section: RailItem, path: string): string | undefined {
  return section.pages
    .filter((page) => under(path, page.to))
    .sort((a, b) => b.to.length - a.to.length)[0]?.to
}

export const OTHER_GROUPS = [
  {
    title: 'Ops',
    icon: Layers,
    items: [
      { href: '/ops?layer=health', label: 'Health', icon: Activity },
      { href: '/ops?layer=approve', label: 'Approve counts', icon: Inbox },
      { href: '/?page=ops', label: 'Ops runbook', icon: FileStack },
      { href: '/cockpit-operational', label: 'Operational cockpit', icon: LayoutDashboard },
    ],
  },
  {
    title: 'Brand',
    icon: Flag,
    items: [
      { href: '/?page=campaigns', label: 'Brand directory', icon: Building2 },
      { href: '/?page=brand-settings', label: 'Brand settings', icon: Palette },
      { href: '/brand/visuals', label: 'Visuals', icon: Palette },
      { href: '/library', label: 'Library', icon: FileStack },
      { href: '/strategy', label: 'Strategy', icon: Flag },
      { href: '/governance', label: 'Governance', icon: ClipboardCheck },
      { href: '/?page=products', label: 'Products', icon: FolderKanban },
      { href: '/?page=agency', label: 'Agency', icon: Building2 },
    ],
  },
  {
    title: 'Labs and tools',
    icon: Sparkles,
    items: [
      { href: '/visualizer', label: 'Visual library', icon: Palette },
      { href: '/meme-lab', label: 'Meme lab', icon: Sparkles },
      { href: '/image-lab', label: 'Image lab', icon: Sparkles },
      { href: '/?page=memes', label: 'Meme Lord', icon: Sparkles },
      { href: '/?page=imagegen', label: 'Image gen', icon: Sparkles },
      { href: '/?page=captions', label: 'Caption studio', icon: FileStack },
      { href: '/?page=hooks', label: 'Hook bank', icon: FileStack },
      { href: '/?page=headlines', label: 'Headlines', icon: FileStack },
      { href: '/?page=billboards', label: 'Billboard lab', icon: FolderKanban },
      { href: '/?page=reddit', label: 'Reddit', icon: Activity },
      { href: '/?page=faqs', label: 'FAQs', icon: FileStack },
      // GEO lives under the SEO group, not as a separate top-level item —
      // it shares the SEO/Measure/Results architecture. /seo-audit is the
      // classic SEO entry; /geo is the Generative Engine Optimisation entry
      // (citations in ChatGPT/Claude/Perplexity/Google AI Overviews).
      { href: '/seo-audit', label: 'SEO audit', icon: Activity },
      { href: '/seo-stack', label: 'SEO stack', icon: Layers },
      { href: '/geo', label: 'GEO', icon: Activity },
    ],
  },
  {
    title: 'Holding pen',
    icon: MoreHorizontal,
    items: [
      { href: '/calendar', label: 'Month grid', icon: CalendarDays },
      { href: '/?page=herman', label: 'Herman demo', icon: CalendarDays },
      { href: '/?page=fleet', label: 'Fleet', icon: Bot },
      { href: '/?page=docs', label: 'Docs', icon: FileStack },
      { href: '/?page=landing', label: 'Landing page', icon: Rocket },
      { href: '/?page=abtests', label: 'A/B tests', icon: Activity },
      { href: '/?page=tenants', label: 'Tenant isolation', icon: Layers },
      { href: '/?page=integrations', label: 'Integrations', icon: Layers },
      { href: '/marketer-workspace.html', label: 'Marketer workspace', icon: LayoutDashboard },
      { href: '/secrets-sync', label: 'Secrets sync', icon: ClipboardCheck },
      { href: '/meta-portal', label: 'Meta portal', icon: Rocket },
      { href: '/home.html', label: 'Old sidebar desk', icon: Flag },
    ],
  },
]
