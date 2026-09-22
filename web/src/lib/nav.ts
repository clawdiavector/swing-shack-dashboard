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
  Sparkles,
  Sun,
} from 'lucide-react'

export type RailItem = {
  to: string
  label: string
  hint: string
  icon: LucideIcon
}

export const RAIL: RailItem[] = [
  { to: '/daily', label: 'Daily', hint: 'Today', icon: Sun },
  { to: '/review', label: 'Review', hint: 'Inbox', icon: Inbox },
  { to: '/create', label: 'Create', hint: 'Studio', icon: Sparkles },
  { to: '/calendar', label: 'Calendar', hint: 'Schedule', icon: CalendarDays },
  { to: '/publish', label: 'Publish', hint: 'Go live', icon: Rocket },
  { to: '/results', label: 'Results', hint: 'What worked', icon: Activity },
  { to: '/other', label: 'Other', hint: 'Leftovers', icon: MoreHorizontal },
]

export const OTHER_GROUPS = [
  {
    title: 'Ops',
    icon: Layers,
    items: [
      { href: '/ops?layer=jobs', label: 'Jobs', icon: ClipboardCheck },
      { href: '/ops?layer=health', label: 'Health', icon: Activity },
      { href: '/ops?layer=agents', label: 'Agents', icon: Bot },
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
      { href: '/seo-audit', label: 'SEO audit', icon: Activity },
      { href: '/seo-stack', label: 'SEO stack', icon: Layers },
    ],
  },
  {
    title: 'Holding pen',
    icon: MoreHorizontal,
    items: [
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
