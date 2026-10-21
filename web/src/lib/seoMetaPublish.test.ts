import { describe, expect, it } from 'vitest'
import { canUndo, modeNote, statusLabel, type MetaChange } from './seoMetaPublish'

const base: MetaChange = {
  id: 'a',
  page: 'Membership',
  link: null,
  before: '',
  after: 'x',
  at: '2026-10-20T04:00:00Z',
  status: 'applied',
  verified: true,
}

describe('canUndo', () => {
  it('is only offered for changes that are live', () => {
    expect(canUndo(base)).toBe(true)
    for (const status of ['dry_run', 'failed', 'undone'] as const) {
      expect(canUndo({ ...base, status })).toBe(false)
    }
  })
})

describe('statusLabel', () => {
  it('says plainly what happened', () => {
    expect(statusLabel(base)).toBe('Changed')
    expect(statusLabel({ ...base, verified: false })).toBe('Changed (not confirmed)')
    expect(statusLabel({ ...base, status: 'dry_run' })).toBe('Would change')
    expect(statusLabel({ ...base, status: 'undone' })).toBe('Undone')
    expect(statusLabel({ ...base, status: 'failed' })).toBe('Did not work')
  })
})

describe('modeNote', () => {
  it('never claims the site changed unless publishing is on', () => {
    expect(modeNote('off')).toMatch(/switched off/)
    expect(modeNote('dry-run')).toMatch(/Nothing on the website has been changed/)
    expect(modeNote('on')).toMatch(/can be undone/)
  })
})
