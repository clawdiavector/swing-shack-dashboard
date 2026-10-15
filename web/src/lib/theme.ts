import { useEffect, useState } from 'react'

export type DeskTheme = 'play' | 'classic'
const KEY = 'cos-theme'

export function readTheme(): DeskTheme {
  try {
    return localStorage.getItem(KEY) === 'classic' ? 'classic' : 'play'
  } catch {
    return 'play'
  }
}

export function applyTheme(theme: DeskTheme) {
  document.documentElement.dataset.theme = theme
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'play' ? '#f3f0ea' : '#0a0f1a')
}

/** Playful is the default. Classic is the original dark desk. */
export function useTheme(): [DeskTheme, () => void] {
  const [theme, setTheme] = useState<DeskTheme>(readTheme)
  useEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      // Private window: the choice lasts until the tab closes.
    }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'play' ? 'classic' : 'play'))]
}
