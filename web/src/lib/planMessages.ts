// Messages for people outside the app, written from a plan so nothing has to be
// retyped: what a facility should shoot, and a plan for someone to sign off.
// Plain text, ready to paste into WhatsApp or an email. Nothing here sends anything.

import { KIND_LABEL, boostBudget, formatDay, formatRand, splitItems, type Plan, type PlanItem } from './plan'

const BRAND_LABEL: Record<string, string> = {
  stick: 'Stick',
  'swing-shack': 'Swing Shack',
  'bag-drop': 'Bag Drop',
}

export function brandLabel(id: string): string {
  return BRAND_LABEL[id] || id
}

/** What to ask for, by the kind of date. These are starting points to edit, not facts. */
const PHOTO_ASK: Record<string, string> = {
  retail_push: 'the products we are promoting: close-ups, the whole range laid out, and a few shown in use',
  sport_event: 'the shop or the range with the feel of the day: the bays, the gear, the screens',
  service_push: 'a real session: the equipment, the process and the result',
  season: 'the shop or space and the products, enough for the first few weeks',
  light: 'one or two good shots of the space or a product',
  standard: 'the shop or space and the products',
}

export function shootSteps(plan: Plan): PlanItem[] {
  return splitItems(plan.items).active.filter((i) => i.kind === 'shoot')
}

function earliest(items: PlanItem[]): string {
  return items.map((i) => i.due).sort()[0] || ''
}

/** The message to a facility asking for what a plan needs shot. `steps` is the
 *  shoot steps it covers (all of them, or one). */
export function shootRequest(opts: {
  plan: Plan
  steps: PlanItem[]
  facility?: string
  sendTo?: string
  today: string
}): string {
  const { plan, steps, facility, sendTo, today } = opts
  const brand = brandLabel(plan.brand_id)
  const kind = plan.event_kind || plan.profile || 'standard'
  const wantsVideo = steps.some((s) => s.needs_real_video)
  const wantsPhotos = steps.some((s) => !s.needs_real_video) || !steps.length
  const by = earliest(steps)
  const lines: string[] = []

  lines.push(`Hi${facility ? ` ${facility}` : ''},`)
  lines.push('')
  lines.push(
    `We are getting ready to promote ${plan.event_name} (${formatDay(plan.event_date)}) at ${brand}, and we need some fresh photos and video from you.`,
  )
  lines.push('')
  lines.push('What we need:')
  if (wantsPhotos) lines.push(`• Photos: about 10 to 15 of ${PHOTO_ASK[kind] || PHOTO_ASK.standard}.`)
  if (wantsVideo) {
    lines.push('• Video: 2 or 3 short clips (10 to 20 seconds each) with a person on camera, talking or doing the thing.')
  }
  lines.push('')
  lines.push('How to shoot it:')
  lines.push('• Hold the phone upright for video. Photos can be upright or sideways.')
  lines.push('• Use daylight or bright light, and wipe the lens first. No filters.')
  lines.push('• Real products and real spaces only. Please do not edit or add effects, we will do that.')
  if (wantsVideo) lines.push('• Anyone on camera needs to be happy to be filmed.')
  lines.push('')
  if (by) {
    lines.push(
      by < today
        ? 'When: as soon as you can, please. We are already behind on this one.'
        : `When: please send everything by ${formatDay(by)}.`,
    )
  }
  lines.push(`Send to: ${sendTo?.trim() || '[where to send it]'}`)
  lines.push('')
  lines.push('Thank you!')
  return lines.join('\n')
}

/** A plan written out for someone to read and approve. */
export function signOffMessage(opts: { plan: Plan; to?: string; from?: string; today: string }): string {
  const { plan, to, from } = opts
  const brand = brandLabel(plan.brand_id)
  const { active } = splitItems(plan.items)
  const boosts = boostBudget(plan.items)
  const lines: string[] = []

  lines.push(`Hi${to ? ` ${to}` : ''},`)
  lines.push('')
  lines.push(
    `Please look over the plan for ${plan.event_name} (${formatDay(plan.event_date)}) at ${brand}${plan.profile_label ? `, shaped as ${plan.profile_label}` : ''}.`,
  )
  lines.push('')
  lines.push('The steps:')
  for (const i of active) {
    lines.push(`• ${formatDay(i.due)}: ${KIND_LABEL[i.kind]}. ${i.title}${i.kind === 'boost' && i.budget ? ` (${formatRand(i.budget)})` : ''}`)
  }
  if (boosts.boosts) {
    lines.push('')
    lines.push(
      boosts.total
        ? `Boost budget in the plan: ${formatRand(boosts.total)}${boosts.missing ? ` (${boosts.missing} boost${boosts.missing === 1 ? ' has' : 's have'} no budget yet)` : ''}. Nothing is spent until we say so.`
        : 'There is a boost in the plan with no budget set yet.',
    )
  }
  lines.push('')
  lines.push('Is this OK to go ahead? Reply "OK", or tell me what to change.')
  if (from) {
    lines.push('')
    lines.push(`Thanks, ${from}`)
  }
  return lines.join('\n')
}

/** Copy text to the clipboard. Falls back to a hidden text box where the
 *  clipboard API is not allowed. Resolves to whether it worked. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to the older way */
  }
  try {
    const box = document.createElement('textarea')
    box.value = text
    box.setAttribute('readonly', '')
    box.style.position = 'fixed'
    box.style.opacity = '0'
    document.body.appendChild(box)
    box.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(box)
    return ok
  } catch {
    return false
  }
}
