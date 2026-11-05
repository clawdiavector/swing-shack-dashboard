// Audit 3 Nov 2026: three small page bugs.
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { BackButton } from '../components/ui'
import { monthListNote } from './cleanCalendar'
import { mergeShelfPayloads, shelfBrandsReady } from './fanOut'

describe('calendar list while a month loads', () => {
  it('says it is loading, not that the month is empty', () => {
    expect(monthListNote(null, '2026-11', 0)).toBe('Loading this month…')
    expect(monthListNote({ month: '2026-10' }, '2026-11', 0)).toBe('Loading this month…')
  })
  it('says the month is empty only once that month has loaded', () => {
    expect(monthListNote({ month: '2026-11' }, '2026-11', 0)).toBe('Nothing here this month.')
    expect(monthListNote({ month: '2026-11' }, '2026-11', 3)).toBe('')
  })
})

describe('Scheduled on first open', () => {
  it('waits for the brands before loading All brands', () => {
    expect(shelfBrandsReady(true, [])).toBe(false)
    expect(shelfBrandsReady(true, ['stick', 'swing-shack'])).toBe(true)
    expect(shelfBrandsReady(false, [])).toBe(true)
  })
  it('does not call no brands a failed load', () => {
    expect(mergeShelfPayloads([], []).ok).not.toBe(false)
    expect(mergeShelfPayloads([], []).error).toBeFalsy()
  })
  it('still reports a failure when every brand failed', () => {
    const out = mergeShelfPayloads([{ brandId: 'stick', payload: { ok: false, error: 'boom' } }], ['stick'])
    expect(out.ok).toBe(false)
  })
})

describe('header on a phone', () => {
  it('keeps the Back label for screen readers but hides the word on small screens', () => {
    const html = renderToStaticMarkup(<BackButton onClick={() => undefined} />)
    expect(html).toContain('aria-label="Back"')
    expect(html).toMatch(/<span class="[^"]*hidden[^"]*sm:inline[^"]*">Back<\/span>/)
  })
})
