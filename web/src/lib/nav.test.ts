import { describe, expect, it } from 'vitest'
import { OTHER_GROUPS, RAIL, SETTINGS, sectionFor, sectionPageFor } from './nav'

describe('rail sections', () => {
  it('has five places, in the order the work happens, with Settings apart', () => {
    expect(RAIL.map((item) => item.label)).toEqual(['Today', 'Plan', 'Create', 'Publish', 'Results'])
    expect(SETTINGS.label).toBe('Settings')
  })

  it('keeps every page that used to be a rail item one click from its section', () => {
    const tabs = [...RAIL, SETTINGS].flatMap((item) => item.pages.map((page) => page.to))
    for (const old of ['/daily', '/inbox', '/week', '/review', '/shelf', '/create', '/calendar/lanes', '/publish', '/results', '/ops', '/other']) {
      expect(tabs, old).toContain(old)
    }
  })

  it('opens each section on its own first tab', () => {
    for (const item of [...RAIL, SETTINGS]) {
      expect(item.pages[0].to).toBe(item.to)
      expect(sectionFor(item.to)).toBe(item)
    }
  })

  it.each([
    ['/review', 'Today'],
    ['/review/long-form/abc', 'Today'],
    ['/inbox', 'Today'],
    ['/week', 'Plan'],
    ['/calendar', 'Plan'],
    ['/calendar/ideas', 'Plan'],
    ['/create/post', 'Create'],
    ['/shelf', 'Publish'],
    ['/publish/long-form/stick/p1', 'Publish'],
    ['/results/week', 'Results'],
    ['/other', 'Settings'],
    ['/brand/visuals', 'Settings'],
    ['/library', 'Settings'],
    ['/geo', 'Settings'],
  ])('%s belongs to %s', (path, label) => {
    expect(sectionFor(path)?.label).toBe(label)
  })

  it('does not confuse /results with /review, or match a bare prefix', () => {
    expect(sectionFor('/reviewer')).toBeUndefined()
    expect(sectionFor('/tool/captions')).toBeUndefined()
  })

  it('highlights the tab the page is on', () => {
    const today = sectionFor('/review')!
    expect(sectionPageFor(today, '/review/long-form')).toBe('/review')
    expect(sectionPageFor(today, '/daily')).toBe('/daily')
    const plan = sectionFor('/calendar')!
    expect(sectionPageFor(plan, '/calendar/lanes')).toBe('/calendar/lanes')
    expect(sectionPageFor(plan, '/calendar/ideas')).toBeUndefined()
  })

  it('every Everything-else link that is an app page sits in a section', () => {
    const appPaths = OTHER_GROUPS.flatMap((group) => group.items.map((item) => item.href.split('?')[0]))
      .filter((path) => ['/ops', '/brand/visuals', '/library', '/geo', '/calendar'].includes(path))
    for (const path of appPaths) expect(sectionFor(path), path).toBeDefined()
  })
})
