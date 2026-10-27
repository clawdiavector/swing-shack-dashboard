// Mail Herman sends to the agent inbox, filed as a Do now or an Idea by the server.
// Text from a mail is shown as plain text only. Nothing in it is run or followed.

import { getJson } from './api'

export type MailKind = 'do_now' | 'idea'

export type Fleshed = {
  concept: { name: string; one_line: string; why_it_works: string; audience: string }
  offer: { what: string; to_confirm: string[] }
  content: Array<{ kind: string; title: string; idea: string; caption_direction: string }>
  shots: string[]
  next_steps: Array<{ step: string; who: string }>
  questions: string[]
  risks: string[]
  generated_at: string
}

export type MailItem = {
  id: string
  kind: MailKind
  subject: string
  /** One idea's own heading. A mail with two ideas makes two items, each with its own title. */
  title?: string
  idea_index?: number
  idea_total?: number
  /** First name of who sent it. Older items have none; only Herman's mail is filed. */
  from_name?: string
  summary: string
  reason: string
  brand: string | null
  date: string | null
  /** What an idea still needs before its plan can be shown: 'brand', 'date'. */
  needs: string[]
  calendar_id: string | null
  calendar_error?: string
  /** Set once its proposed plan has been made; the plan itself is found by brief_id. */
  plan_id?: string
  brief_id?: string
  /** The idea built out into a concept, content, shots and next steps. */
  fleshed?: Fleshed
  /** Set when the card has asked Claude to write the idea out; cleared once it is written. */
  flesh_requested_at?: string
  received_at: string
}

export type MailIntake = {
  ok: boolean
  watching: { inbox: boolean; senders: boolean; notice: boolean }
  do_now: MailItem[]
  ideas: MailItem[]
}

export const fetchMailIntake = (brand?: string) =>
  getJson<MailIntake>(`/api/mail-intake?brand=${encodeURIComponent(brand || 'all')}`)

type ActResult = { ok: boolean; error?: string; item?: MailItem }

async function act(id: string, action: string, body: unknown): Promise<ActResult> {
  try {
    const res = await fetch(`/api/mail-intake/${encodeURIComponent(id)}/${action}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (res.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
      return { ok: false, error: 'Please sign in again.' }
    }
    const j = (await res.json().catch(() => ({}))) as ActResult
    if (!res.ok || j.ok === false) return { ok: false, error: j.error || `Something went wrong (${res.status}).` }
    return j
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.' }
  }
}

export const markMail = (id: string, status: 'done' | 'dismissed') => act(id, 'status', { status })
export const moveMail = (id: string, kind: MailKind) => act(id, 'kind', { kind })

/** Make the idea's proposed plan. A draft: nothing goes on the calendar until the plan is placed. */
export const mailIdeaPlan = (id: string, brand: string, date: string, force = false) =>
  act(id, 'plan', { brand, date, force })

/** Ask Claude to build the idea out into a whole concept. Claude writes it in a session; it then shows on the card. */
export const mailIdeaAsk = (id: string, brand: string, date: string) => act(id, 'ask', { brand, date })

/** The card's heading: its own title, else the mail's subject. */
export const ideaHeading = (m: MailItem) => m.title || m.subject || '(no subject)'
