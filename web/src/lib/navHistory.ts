export type NavAction = 'POP' | 'PUSH' | 'REPLACE'

const STORAGE_KEY = 'cos.navTrail'
const MAX = 40

/** Keep the in-app trail aligned with browser history, including replace redirects. */
export function applyNav(stack: string[], path: string, action: NavAction): string[] {
  if (!path.startsWith('/')) return stack
  if (stack[stack.length - 1] === path) return stack

  if (action === 'REPLACE') {
    if (stack.length === 0) return [path]
    return [...stack.slice(0, -1), path]
  }

  if (action === 'POP') {
    if (stack.length >= 2 && stack[stack.length - 2] === path) return stack.slice(0, -1)
    const idx = stack.lastIndexOf(path)
    if (idx >= 0) return stack.slice(0, idx + 1)
    return [path]
  }

  const next = [...stack, path]
  return next.length > MAX ? next.slice(next.length - MAX) : next
}

/** Page the user was on before `current`, when the trail knows it. */
export function previousPath(stack: string[], current: string): string | null {
  if (stack.length >= 2 && stack[stack.length - 1] === current) return stack[stack.length - 2]
  if (stack.length >= 1 && stack[stack.length - 1] !== current) return stack[stack.length - 1]
  return null
}

export function pageLabel(path: string): string {
  const p = path.split('?')[0]
  if (p.startsWith('/week')) return 'This week'
  if (p.startsWith('/inbox')) return 'Inbox'
  if (p.startsWith('/review')) return 'Review'
  if (p.startsWith('/daily')) return 'Today'
  if (p.startsWith('/library')) return 'Library'
  if (p.startsWith('/calendar')) return 'Calendar'
  if (p.startsWith('/publish')) return 'Publish'
  if (p.startsWith('/create')) return 'Studio'
  if (p.startsWith('/results') || p.startsWith('/geo')) return 'Results'
  if (p.startsWith('/shelf')) return 'Shelf'
  if (p.startsWith('/ops')) return 'Ops'
  if (p.startsWith('/other') || p.startsWith('/tool') || p.startsWith('/desk')) return 'Other'
  if (p.startsWith('/brand')) return 'Brand'
  return 'the previous page'
}

export function readNavTrail(): string[] {
  if (typeof sessionStorage === 'undefined') return []
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

export function recordNav(path: string, action: NavAction): string[] {
  const next = applyNav(readNavTrail(), path, action)
  if (typeof sessionStorage !== 'undefined') {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* private mode or quota — back still uses the in-memory result for this call */
    }
  }
  return next
}
