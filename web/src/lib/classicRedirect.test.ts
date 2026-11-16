import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { classicRedirect, retiredLabel } from './classicRedirect'
import { OTHER_GROUPS } from './nav'

describe('classicRedirect', () => {
  it('sends old ?page= links to their new page', () => {
    expect(classicRedirect('/', '?page=learning')).toBe('/app/results/worked')
    expect(classicRedirect('/', '?page=memes')).toBe('/app/create/memes?tab=lord')
    expect(classicRedirect('/', '?page=review')).toBe('/app/review')
    expect(classicRedirect('/', '?page=ops')).toBe('/app/ops')
  })

  it('keeps the other query values, and they win over defaults', () => {
    expect(classicRedirect('/', '?page=socials&brand=stick')).toBe('/app/publish/socials?brand=stick')
    expect(classicRedirect('/', '?page=gbp&tab=drafts')).toBe('/app/publish/gbp?tab=drafts')
  })

  it('sends retired pages to Everything else with a note, never a blank page', () => {
    expect(classicRedirect('/', '?page=herman')).toBe('/app/other?retired=herman')
    expect(classicRedirect('/home.html', '?page=fleet&embed=1')).toBe('/app/ops?tab=agents&embed=1')
    expect(classicRedirect('/home.html', '?page=faqs')).toBe('/app/other?retired=faqs')
    expect(classicRedirect('/strategy', '?brand=stick')).toBe('/app/other?retired=strategy')
  })

  it('sends a bare / or /home.html to Today', () => {
    expect(classicRedirect('/', '')).toBe('/app/daily')
    expect(classicRedirect('/home.html', '')).toBe('/app/daily')
  })

  it('leaves the new app alone', () => {
    expect(classicRedirect('/app/daily', '')).toBeNull()
    expect(classicRedirect('/app/results/worked', '?page=2')).toBeNull()
  })

  it('names retired pages in plain words', () => {
    expect(retiredLabel('herman')).toBe('Herman demo')
    expect(retiredLabel('something-odd')).toBe('something-odd')
  })
})

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : []
  })
}

describe('no link opens a blank Classic page', () => {
  it('no app file links to /?page=', () => {
    const src = join(__dirname, '..')
    const offenders = sourceFiles(src)
      .filter((f) => !f.endsWith('classicRedirect.ts'))
      .filter((f) => readFileSync(f, 'utf8').includes('/?page='))
    expect(offenders).toEqual([])
  })

  it('Everything else lists no page that opens blank', () => {
    const hrefs = OTHER_GROUPS.flatMap((g) => g.items.map((i) => i.href))
    const dead = hrefs.filter((h) => h.startsWith('/?page=') || h === '/strategy' || h === '/home.html')
    expect(dead).toEqual([])
  })
})
