import { matchTool, toolTo } from './tools'

const SPA_PREFIXES = ['/daily', '/review', '/create', '/calendar', '/publish', '/results', '/other', '/desk', '/tool']

function isSpaPath(path: string) {
  return SPA_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`))
}

/** Keep operators inside Campaign OS chrome. Classic tools load at /desk. */
export function toDesk(href: string): string {
  if (!href || href === '#') return '/desk'
  if (href.startsWith('/app/')) {
    const rest = href.slice(4) || '/daily'
    return isSpaPath(rest.split('?')[0]) ? rest : toDesk(rest)
  }
  let url: URL
  try {
    url = new URL(href, 'https://campaign-os.local')
  } catch {
    return '/desk'
  }
  if (isSpaPath(url.pathname)) {
    return `${url.pathname}${url.search}`
  }
  if (url.pathname === '/' && !url.searchParams.get('page')) {
    return '/daily'
  }
  const tool = matchTool(url)
  if (tool) {
    return toolTo(tool.slug, {
      item: url.searchParams.get('item') || undefined,
      asset: url.searchParams.get('asset') || url.searchParams.get('id') || undefined,
      campaign: url.searchParams.get('campaign') || undefined,
      brand: url.searchParams.get('brand') || undefined,
      title: url.searchParams.get('title') || undefined,
      from: url.searchParams.get('from') || undefined,
      date: url.searchParams.get('date') || undefined,
    })
  }
  const src = classicSrc(url)
  return `/desk?src=${encodeURIComponent(src)}`
}

function classicSrc(url: URL) {
  const page = url.searchParams.get('page')
  if (url.pathname === '/' || url.pathname === '/home.html') {
    const next = new URL('/home.html', url.origin)
    if (page) next.searchParams.set('page', page)
    next.searchParams.set('embed', '1')
    const brand = url.searchParams.get('brand')
    if (brand) next.searchParams.set('brand', brand)
    return `${next.pathname}${next.search}`
  }
  const next = new URL(url.href)
  next.searchParams.set('embed', '1')
  return `${next.pathname}${next.search}`
}

export function deskSrcFromSearch(search: string) {
  const raw = new URLSearchParams(search).get('src') || '/home.html?embed=1'
  if (!raw.startsWith('/') || raw.startsWith('//')) return '/home.html?embed=1'
  return raw
}
