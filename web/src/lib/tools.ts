export type ToolDef = {
  slug: string
  label: string
  hint: string
  from: string
  page?: string
  path?: string
  native?: string
}

export const TOOLS: ToolDef[] = [
  {
    slug: 'buildpost',
    page: 'buildpost',
    label: 'Build a post',
    hint: 'Caption, visual, hook',
    from: '/create',
    native: '/create/post',
  },
  {
    slug: 'captions',
    page: 'captions',
    label: 'Captions',
    hint: 'IG / FB / LinkedIn',
    from: '/create',
    native: '/create/captions',
  },
  {
    slug: 'headlines',
    page: 'headlines',
    label: 'Headlines',
    hint: 'Punchy titles',
    from: '/create',
    native: '/create/copy?tab=headlines',
  },
  {
    slug: 'hooks',
    page: 'hooks',
    label: 'Hook bank',
    hint: 'Openers',
    from: '/create',
    native: '/create/copy?tab=hooks',
  },
  {
    slug: 'ctas',
    page: 'ctas',
    label: 'CTAs',
    hint: 'Ask for the click',
    from: '/create',
    native: '/create/copy?tab=ctas',
  },
  {
    slug: 'hashtagseo',
    page: 'hashtagseo',
    label: 'Hashtags',
    hint: 'Discoverability',
    from: '/create',
    native: '/create/copy?tab=hashtags',
  },
  {
    slug: 'imagegen',
    page: 'imagegen',
    label: 'Image gen',
    hint: 'Generate a still',
    from: '/create',
    native: '/create/images?tab=generate',
  },
  {
    slug: 'image-lab',
    path: '/image-lab',
    label: 'Image lab',
    hint: 'Iterate and crop',
    from: '/create',
    native: '/create/images?tab=lab',
  },
  {
    slug: 'visualizer',
    path: '/visualizer',
    label: 'Visual library',
    hint: 'Past assets',
    from: '/create',
    native: '/create/images?tab=library',
  },
  {
    slug: 'memes',
    page: 'memes',
    label: 'Meme Lord',
    hint: 'Classic meme desk',
    from: '/create',
    native: '/create/memes?tab=lord',
  },
  {
    slug: 'meme-lab',
    path: '/meme-lab',
    label: 'Meme lab',
    hint: 'Templates',
    from: '/create',
    native: '/create/memes?tab=lab',
  },
  {
    slug: 'library',
    page: 'library',
    label: 'Copy library',
    hint: 'Reuse a winner',
    from: '/create',
    native: '/create/copy?tab=library',
  },
  {
    slug: 'calendar',
    page: 'calendar',
    label: 'Month grid',
    hint: 'Every brand, one month',
    from: '/calendar',
    native: '/calendar',
  },
  {
    slug: 'planning',
    page: 'planning',
    label: 'Planning',
    hint: 'Themes and lanes',
    from: '/calendar',
    native: '/calendar/lanes',
  },
  {
    slug: 'ideas',
    page: 'ideas',
    label: 'Ideas',
    hint: 'Backlog to park',
    from: '/calendar',
    native: '/calendar/ideas',
  },
  {
    slug: 'publish',
    page: 'publish',
    label: 'Publish queue',
    hint: 'What ships next',
    from: '/publish',
    native: '/publish/queue',
  },
  {
    slug: 'postiz',
    page: 'postiz',
    label: 'Postiz',
    hint: 'Scheduler',
    from: '/publish',
    native: '/publish/postiz',
  },
  {
    slug: 'gbp',
    page: 'gbp',
    label: 'GBP',
    hint: 'Google Business Profile',
    from: '/publish',
    native: '/publish/gbp?tab=plans',
  },
  {
    slug: 'gmb',
    page: 'gmb',
    label: 'GBP drafts',
    hint: 'Pending listings',
    from: '/publish',
    native: '/publish/gbp?tab=drafts',
  },
  { slug: 'socials', page: 'socials', label: 'Socials', hint: 'What’s live', from: '/daily' },
  {
    slug: 'accounts',
    path: '/connected-accounts',
    label: 'Accounts',
    hint: 'Connected channels',
    from: '/publish',
    native: '/ops?tab=accounts',
  },
  { slug: 'weekly-report', path: '/weekly-report', label: 'This week', hint: 'Weekly report', from: '/results' },
  { slug: 'insights', page: 'insights', label: 'Insights', hint: 'What worked', from: '/results' },
  { slug: 'performance', page: 'performance', label: 'Reach', hint: 'Performance', from: '/results' },
  { slug: 'learning', page: 'learning', label: 'Learnings', hint: 'Recipes', from: '/results' },
  { slug: 'trends', page: 'trends', label: 'Trends', hint: 'What is moving', from: '/results' },
  { slug: 'seo', page: 'seo', label: 'SEO', hint: 'Rankings and audit', from: '/results' },
  { slug: 'review', page: 'review', label: 'Classic inbox', hint: 'Old review wall', from: '/review' },
]

export const TOOL_BY_SLUG = Object.fromEntries(TOOLS.map((t) => [t.slug, t])) as Record<string, ToolDef>

const PATH_TO_SLUG: Record<string, string> = {}
for (const tool of TOOLS) {
  if (tool.path) PATH_TO_SLUG[tool.path] = tool.slug
}

export function matchTool(url: URL): ToolDef | null {
  const page = url.searchParams.get('page')
  if (page && TOOL_BY_SLUG[page]) return TOOL_BY_SLUG[page]
  const path = url.pathname.replace(/\.html$/, '')
  const slug = PATH_TO_SLUG[path]
  return slug ? TOOL_BY_SLUG[slug] : null
}

export function toolTo(slug: string, extra?: Record<string, string | undefined>) {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(extra || {})) {
    if (value) q.set(key, value)
  }
  const qs = q.toString()
  return qs ? `/tool/${slug}?${qs}` : `/tool/${slug}`
}

/** Merge catalog default query on `native` with inbound deep-link params (inbound wins). */
export function mergeNativeTarget(native: string, inbound: URLSearchParams): string {
  const qIndex = native.indexOf('?')
  const path = qIndex >= 0 ? native.slice(0, qIndex) : native
  const merged = new URLSearchParams(qIndex >= 0 ? native.slice(qIndex + 1) : '')
  inbound.forEach((value, key) => merged.set(key, value))
  const qs = merged.toString()
  return qs ? `${path}?${qs}` : path
}

export function toolEmbedSrc(tool: ToolDef, params: URLSearchParams) {
  const keep = ['item', 'asset', 'campaign', 'brand', 'id', 'date']
  if (tool.page) {
    const next = new URLSearchParams()
    next.set('page', tool.page)
    next.set('embed', '1')
    for (const key of keep) {
      const value = params.get(key)
      if (value) next.set(key === 'id' ? 'asset' : key, value)
    }
    return `/home.html?${next}`
  }
  const path = tool.path || '/'
  const next = new URLSearchParams()
  next.set('embed', '1')
  for (const key of keep) {
    const value = params.get(key)
    if (value) next.set(key, value)
  }
  const qs = next.toString()
  return qs ? `${path}?${qs}` : path
}

export function parentLabel(from: string) {
  if (from.startsWith('/create')) return 'Studio'
  if (from.startsWith('/review')) return 'Inbox'
  if (from.startsWith('/calendar')) return 'Calendar'
  if (from.startsWith('/publish')) return 'Publish'
  if (from.startsWith('/results')) return 'Results'
  if (from.startsWith('/daily')) return 'Daily'
  return 'Desk'
}
