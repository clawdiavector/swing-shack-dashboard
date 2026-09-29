import { describe, expect, it, vi } from 'vitest'
import {
  buildMonthGridCells,
  clampPlanningTimelineYear,
  filterMonthItemsByLane,
  formatLocalIso,
  formatTimelineWindowLabel,
  localTodayIso,
  monthlyThemeLabel,
  shiftPlanningTimelineYear,
} from './planning'
import type { PlanningMonthItem } from './planningTypes'

describe('buildMonthGridCells B2 padding ISO', () => {
  it('maps November 2026 leading padding to October dates', () => {
    const cells = buildMonthGridCells(2026, 11, '2026-11-01')
    const first = cells[0]
    expect(first.inMonth).toBe(false)
    expect(first.iso).toMatch(/^2026-10-/)
    expect(first.iso).toBe('2026-10-26')
  })

  it('maps trailing padding into December for November 2026', () => {
    const cells = buildMonthGridCells(2026, 11, '2026-11-01')
    const last = cells[cells.length - 1]
    expect(last.inMonth).toBe(false)
    expect(last.iso).toMatch(/^2026-12-/)
  })

  it('January 2026 leading cells resolve to December 2025', () => {
    const cells = buildMonthGridCells(2026, 1, '2026-01-15')
    const padding = cells.filter((c) => !c.inMonth && c.iso < '2026-01-01')
    expect(padding.length).toBeGreaterThan(0)
    expect(padding.every((c) => c.iso.startsWith('2025-12-'))).toBe(true)
  })
})

describe('localTodayIso B3', () => {
  it('uses local calendar parts not UTC ISO slice', () => {
    const d = new Date(2026, 8, 24, 1, 30, 0)
    expect(localTodayIso(d)).toBe('2026-09-24')
    expect(d.toISOString().slice(0, 10)).toBe('2026-09-23')
  })

  it('formatLocalIso matches local midnight boundary', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 0, 15, 23, 45, 0))
    expect(formatLocalIso(new Date())).toBe('2026-01-15')
    vi.useRealTimers()
  })
})

describe('monthlyThemeLabel', () => {
  it('returns string as-is', () => {
    expect(monthlyThemeLabel('Hero month')).toBe('Hero month')
  })

  it('prefers theme then question on object', () => {
    expect(
      monthlyThemeLabel({
        theme: 'What belongs in your bag?',
        question: 'When every club…',
      }),
    ).toBe('What belongs in your bag?')
    expect(monthlyThemeLabel({ question: 'Only question' })).toBe('Only question')
  })

  it('returns empty for null, empty string, or unusable object', () => {
    expect(monthlyThemeLabel(null)).toBe('')
    expect(monthlyThemeLabel('')).toBe('')
    expect(monthlyThemeLabel({ lanes_emphasis: ['product'] })).toBe('')
  })
})

describe('filterMonthItemsByLane', () => {
  const items: PlanningMonthItem[] = [
    { title: 'A', lane: 'fitting' },
    { title: 'B', lane: 'retail' },
    { title: 'C', lane: 'fitting' },
  ]

  it('returns all when filter empty', () => {
    expect(filterMonthItemsByLane(items, '')).toHaveLength(3)
  })

  it('narrows to one lane', () => {
    expect(filterMonthItemsByLane(items, 'fitting')).toHaveLength(2)
  })
})

describe('formatTimelineWindowLabel', () => {
  it('uses calendar year at 12M zoom instead of rolling offset', () => {
    expect(
      formatTimelineWindowLabel({
        zoomDays: 365,
        yearInt: 2026,
        offsetDays: 365,
        todayIso: '2026-09-29',
      }),
    ).toBe('Jan 1 → Dec 31 · 2026')
  })

  it('uses rolling window for sub-year zooms', () => {
    expect(
      formatTimelineWindowLabel({
        zoomDays: 90,
        yearInt: 2026,
        offsetDays: 0,
        todayIso: '2026-09-29',
      }),
    ).toBe('Sep 29 → Dec 28')
  })

  it('advances rolling window start when offset increases', () => {
    expect(
      formatTimelineWindowLabel({
        zoomDays: 90,
        yearInt: 2026,
        offsetDays: 90,
        todayIso: '2026-09-29',
      }),
    ).toBe('Dec 28 → Mar 28 \'27')
  })
})

describe('shiftPlanningTimelineYear', () => {
  it('clamps to supported planning years', () => {
    expect(shiftPlanningTimelineYear(2026, -1)).toBeNull()
    expect(shiftPlanningTimelineYear(2026, 1)).toBe(2027)
    expect(shiftPlanningTimelineYear(2027, 1)).toBeNull()
  })

  it('clampPlanningTimelineYear keeps value in range', () => {
    expect(clampPlanningTimelineYear(2025)).toBe(2026)
    expect(clampPlanningTimelineYear(2028)).toBe(2027)
    expect(clampPlanningTimelineYear(2026)).toBe(2026)
  })
})
