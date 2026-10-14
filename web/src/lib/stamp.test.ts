import { describe, expect, it } from 'vitest'
import { isoDate, stampLabel } from './stamp'

function daysFromNow(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return isoDate(d)
}

describe('stampLabel', () => {
  it('says a past go-live date was due, not that it goes out', () => {
    expect(stampLabel('goes_out', daysFromNow(-1))).toBe('Was due')
    expect(stampLabel('goes_out', '2026-08-10')).toBe('Was due')
  })

  it('keeps "Goes out" for today, the future and a missing date', () => {
    expect(stampLabel('goes_out', daysFromNow(0))).toBe('Goes out')
    expect(stampLabel('goes_out', daysFromNow(3))).toBe('Goes out')
    expect(stampLabel('goes_out')).toBe('Goes out')
  })

  it('leaves the other kinds alone', () => {
    expect(stampLabel('created', daysFromNow(-5))).toBe('Landed')
    expect(stampLabel('as_of')).toBe('As of')
  })
})
