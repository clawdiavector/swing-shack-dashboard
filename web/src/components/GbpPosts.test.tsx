import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { nextStep, postStage, PostCard, problemWords, StepBar, type PostHandlers } from './GbpPosts'

const handlers: PostHandlers = {
  onApprove: () => {},
  onUnapprove: () => {},
  onPublish: () => {},
  onDelete: () => {},
  onPhoto: () => {},
  onSave: async () => true,
}
const plain = (s: string) => s.replace(/[  ]/g, ' ')
const card = (d: Parameters<typeof PostCard>[0]['d']) =>
  plain(renderToStaticMarkup(<PostCard d={d} busy={false} terms={[]} handlers={handlers} />))

const draft = { id: 'a', title: 'Fit first', body: 'Custom club fitting.', cta: 'Book', link: 'https://stickgolf.co.za/', imageUrl: '/x.jpg' }

describe('postStage', () => {
  it('puts a new draft in check, approved in ready, sent ones in sent', () => {
    expect(postStage({ ...draft, status: 'draft' })).toBe('check')
    expect(postStage({ ...draft })).toBe('check')
    expect(postStage({ ...draft, status: 'approved' })).toBe('ready')
    expect(postStage({ ...draft, status: 'scheduled' })).toBe('sent')
    expect(postStage({ ...draft, status: 'published' })).toBe('sent')
  })
})

describe('nextStep', () => {
  it('tells her the one next thing to do', () => {
    expect(nextStep({ check: 3, ready: 0, sent: 0 })).toContain('3 posts need your check')
    expect(nextStep({ check: 3, ready: 1, sent: 0 })).toContain('1 post is approved')
    expect(nextStep({ check: 0, ready: 0, sent: 2 })).toContain('New post')
  })
})

describe('problemWords', () => {
  it('turns server codes into plain words', () => {
    expect(problemWords(['photo_missing', 'link_missing'])).toEqual(['needs a photo', 'needs a link'])
  })
})

describe('StepBar', () => {
  it('shows the three steps with their counts', () => {
    const out = plain(renderToStaticMarkup(<StepBar tab="check" counts={{ check: 2, ready: 1, sent: 0 }} onChange={() => {}} />))
    expect(out).toContain('To check')
    expect(out).toContain('(2)')
    expect(out).toContain('Ready to send')
    expect(out).toContain('Sent')
  })
})

describe('PostCard', () => {
  it('locks Approve until the photo box is ticked', () => {
    const out = card(draft)
    expect(out).toContain('The photo shows what the text says')
    expect(out).toMatch(/<button[^>]*disabled[^>]*>Approve<\/button>/)
    expect(out).toContain('Tick the box above to unlock Approve.')
  })
  it('says what is missing and keeps Approve locked', () => {
    const out = card({ ...draft, imageUrl: '', link: '' })
    expect(out).toContain('needs a photo, needs a link')
    expect(out).toContain('Add a photo')
  })
  it('offers Publish on an approved post, with no Approve button', () => {
    const out = card({ ...draft, status: 'approved' })
    expect(out).toContain('Publish to Google')
    expect(out).not.toContain('>Approve<')
    expect(out).toContain('Move back to “To check”')
  })
  it('shows a sent post with no buttons to act on it', () => {
    const out = card({ ...draft, status: 'scheduled' })
    expect(out).toContain('Sent to Google')
    expect(out).not.toContain('Publish to Google<')
    expect(out).not.toContain('Change photo')
  })
})
