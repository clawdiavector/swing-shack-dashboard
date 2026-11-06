// A shorter Today (5 Nov 2026): Herman's ideas opened their whole plan (58% of the page),
// every alert date showed, and Stories, What worked and Shortcuts repeated other tabs.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { IdeaCard } from '../components/MailToday'
import { momentsForToday } from '../components/MomentsToday'
import { NextToApproveView } from '../components/NextToApprove'
import type { CalendarAlert } from './calendarAlerts'
import type { InboxItem } from './api'
import type { MailItem } from './mailIntake'
import { splitAlerts } from './shorterToday'

const alert = (n: number): CalendarAlert => ({
  event_key: `k${n}`, name: `Date ${n}`, date: '2026-11-15', days: n, tier: 'A-PIN', level: 'warn',
  state: 'no_plan', brief_id: null, plan_id: null, brand_id: 'stick', message: `Date ${n}`,
})

describe('alert banner on Today', () => {
  it('shows the 3 closest and counts the rest', () => {
    const { shown, more } = splitAlerts(Array.from({ length: 9 }, (_, i) => alert(i)), 3)
    expect(shown.map((a) => a.event_key)).toEqual(['k0', 'k1', 'k2'])
    expect(more).toBe(6)
  })
  it('shows them all without a limit', () => {
    const { shown, more } = splitAlerts([alert(1), alert(2)])
    expect(shown).toHaveLength(2)
    expect(more).toBe(0)
  })
})

describe('Herman’s ideas on Today', () => {
  it('keeps the built-out idea closed until asked', () => {
    const m = {
      id: 'm1', kind: 'idea', subject: 'Ladies BF', summary: 'Deals for ladies', reason: '', brand: 'stick',
      date: null, needs: [], calendar_id: null,
      fleshed: { concept: { name: 'Fit first, then the deal', one_line: 'A fitting first.' } },
    } as unknown as MailItem
    const html = renderToStaticMarkup(<IdeaCard m={m} run={async () => undefined} />)
    expect(html).toContain('Show the suggested idea')
    expect(html).not.toContain('data-testid="idea-built"')
    expect(html).not.toContain('Fit first, then the deal')
  })
})

describe('moments on Today', () => {
  const live = (title: string, over: Record<string, unknown> = {}) => ({ title, source: 's', act_today: true, ...over })
  it('shows at most 2, and never one marked not to joke about', () => {
    const out = momentsForToday([
      live('Phala Phala farm heist', { skip_joke: true }),
      live('Boks to Italy'),
      live('Sun City parkrun'),
      live('Third'),
      live('Old news', { act_today: false }),
    ] as never)
    expect(out.map((l) => l.title)).toEqual(['Boks to Italy', 'Sun City parkrun'])
  })
})

describe('next to approve', () => {
  const item = (id: string): InboxItem => ({ id, type: 'draft_asset', title: `Post ${id}`, status: 'pending' }) as InboxItem
  it('lists up to 3 drafts with an Approve button each and links to the rest', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <NextToApproveView items={['a', 'b', 'c', 'd'].map(item)} total={14} busy="" onApprove={() => undefined} />
      </MemoryRouter>,
    )
    expect(html.match(/>Approve</g)).toHaveLength(3)
    expect(html).toContain('Post a')
    expect(html).not.toContain('Post d')
    expect(html).toContain('See all 14')
  })
  it('says the desk is clear when nothing waits', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <NextToApproveView items={[]} total={0} busy="" onApprove={() => undefined} />
      </MemoryRouter>,
    )
    expect(html).toContain('Nothing waiting for a yes')
  })
})
