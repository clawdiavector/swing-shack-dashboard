/**
 * Old Classic links (`/?page=…`, `/home.html`, `/strategy`).
 *
 * Since 30 Sep 2026 the server serves this app's build for those URLs, and
 * the router only draws under /app, so they opened a blank page. main.tsx
 * calls classicRedirect() before rendering and replaces the URL with the new
 * page, or with Everything else plus a "retired" note.
 */

const NATIVE: Record<string, string> = {
  buildpost: '/app/create/post',
  create: '/app/create',
  captions: '/app/create/captions',
  headlines: '/app/create/copy?tab=headlines',
  hooks: '/app/create/copy?tab=hooks',
  ctas: '/app/create/copy?tab=ctas',
  hashtagseo: '/app/create/copy?tab=hashtags',
  library: '/app/create/copy?tab=library',
  imagegen: '/app/create/images?tab=generate',
  memes: '/app/create/memes?tab=lord',
  calendar: '/app/calendar',
  ideas: '/app/calendar/ideas',
  planning: '/app/calendar/lanes',
  review: '/app/review',
  publish: '/app/publish/queue',
  postiz: '/app/publish/postiz',
  gbp: '/app/publish/gbp?tab=plans',
  gmb: '/app/publish/gbp?tab=drafts',
  socials: '/app/publish/socials',
  insights: '/app/results/worked?tab=posts',
  learning: '/app/results/worked',
  performance: '/app/results/worked',
  trends: '/app/results/trends',
  seo: '/app/results/seo',
  'seo-audit': '/seo-audit',
  ops: '/app/ops',
  fleet: '/app/ops?tab=agents',
  agents: '/app/ops?tab=agents',
  metaoauth: '/meta-portal',
}

const RETIRED_LABELS: Record<string, string> = {
  abtests: 'A/B tests',
  agency: 'Agency',
  billboards: 'Billboard lab',
  'brand-settings': 'Brand settings',
  brief: 'Morning brief',
  campaigns: 'Brand directory',
  docs: 'Docs',
  faqs: 'FAQs',
  herman: 'Herman demo',
  integrations: 'Integrations',
  landing: 'Landing page',
  onboarding: 'Onboarding',
  products: 'Products',
  reddit: 'Reddit',
  strategy: 'Strategy',
  tenants: 'Tenant isolation',
}

export function retiredLabel(slug: string): string {
  return RETIRED_LABELS[slug] ?? slug
}

function withQuery(target: string, inbound: URLSearchParams): string {
  const q = target.indexOf('?')
  const path = q >= 0 ? target.slice(0, q) : target
  const merged = new URLSearchParams(q >= 0 ? target.slice(q + 1) : '')
  inbound.forEach((value, key) => {
    if (key !== 'page') merged.set(key, value)
  })
  const qs = merged.toString()
  return qs ? `${path}?${qs}` : path
}

/** Where an old Classic URL should go, or null when the URL is already in the app. */
export function classicRedirect(pathname: string, search: string): string | null {
  if (pathname === '/strategy') return `/app/other?retired=strategy`
  if (pathname !== '/' && pathname !== '/home.html') return null
  const params = new URLSearchParams(search)
  const page = params.get('page')
  if (!page) return '/app/daily'
  const native = NATIVE[page]
  if (native) return withQuery(native, params)
  return `/app/other?retired=${encodeURIComponent(page)}`
}
