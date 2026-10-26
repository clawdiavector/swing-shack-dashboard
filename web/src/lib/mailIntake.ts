// Mail Herman sends to the agent inbox, filed as a Do now or an Idea by the server.
// Text from a mail is shown as plain text only. Nothing in it is run or followed.

import { getJson, postJson } from './api'

export type MailKind = 'do_now' | 'idea'

export type MailItem = {
  id: string
  kind: MailKind
  subject: string
  summary: string
  reason: string
  brand: string | null
  date: string | null
  /** What an idea still needs before it can go on the calendar: 'brand', 'date'. */
  needs: string[]
  calendar_id: string | null
  calendar_error?: string
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
    return await postJson<ActResult>(`/api/mail-intake/${encodeURIComponent(id)}/${action}`, body)
  } catch (e: unknown) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network problem.' }
  }
}

export const markMail = (id: string, status: 'done' | 'dismissed') => act(id, 'status', { status })
export const moveMail = (id: string, kind: MailKind) => act(id, 'kind', { kind })
export const mailToCalendar = (id: string, brand: string, date: string) => act(id, 'to-calendar', { brand, date })
