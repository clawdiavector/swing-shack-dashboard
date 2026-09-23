import { describe, expect, it, vi } from 'vitest'
import {
  buildMonthGridCells,
  filterMonthItemsByLane,
  formatLocalIso,
  localTodayIso,
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
