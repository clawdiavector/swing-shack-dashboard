import { Loader2 } from 'lucide-react'
import { EventTypeIcon } from '../../../components/EventTypeIcon'
import { MessageComposer } from './MessageComposer'
import { shootRequest, shootSteps, signOffMessage } from '../../../lib/planMessages'
import { notifyAlertsChanged } from '../../../lib/calendarAlerts'
import { useCallback, useEffect, useState } from 'react'
import {
  KIND_LABEL,
  KIND_ORDER,
  boostBudget,
  formatRand,
  PROFILE_OPTIONS,
  actorName,
  addPlanItem,
  approveBlocker,
  approvePlan,
  placePlan,
  unplacePlan,
  dueLabel,
  editPlanItem,
  formatDay as formatPlanDate,
  findPlan,
  proposePlan,
  savedActorName,
  reopenPlan,
  splitItems,
  todayIso,
  type Plan,
  type PlanItem,
  type PlanItemKind,
  type PlanItemPatch,
  type PlanProfile,
  type PlanResult,
} from '../../../lib/plan'

const btn =
  'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold disabled:opacity-60'
const btnYel = `${btn} border-yel/40 bg-yel/15 text-yel hover:bg-yel/25`
const btnQuiet = `${btn} border-bd text-tx2 hover:text-tx`
const field = 'rounded border border-bd bg-bg px-2 py-1 text-sm text-tx'

function ItemRow({
  item,
  today,
  locked,
  onSave,
  onCopyRequest,
}: {
  item: PlanItem
  today: string
  locked: boolean
  onSave: (patch: PlanItemPatch) => Promise<string | null>
  /** Shoot steps only: open the message to whoever is doing the shoot. */
  onCopyRequest?: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(item.title)
  const [due, setDue] = useState(item.due)
  const [note, setNote] = useState(item.note)
  const [budget, setBudget] = useState(item.budget ? String(item.budget) : '')
  const [err, setErr] = useState<string | null>(null)
  const done = item.status === 'done'

  async function save(patch: PlanItemPatch) {
    setErr(null)
    const e = await onSave(patch)
    if (e) setErr(e)
    else setEditing(false)
  }

  if (editing) {
    return (
      <li className="space-y-2 rounded-md border border-yel/30 bg-bg2 px-3 py-2" data-testid="plan-item-editing">
        <div className="flex flex-wrap gap-2">
          <input
            aria-label="What to do"
            className={`${field} min-w-0 flex-1`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            aria-label="Due date"
            type="date"
            className={field}
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </div>
        <textarea
          aria-label="Note"
          className={`${field} w-full`}
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {item.kind === 'boost' ? (
          <label className="block text-xs text-tx2">
            Planned budget (rand)
            <input
              aria-label="Planned budget in rand"
              data-testid="plan-budget-input"
              inputMode="decimal"
              placeholder="e.g. 1500"
              className={`${field} mt-1 block w-40`}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
            <span className="mt-1 block text-[11px] text-tx3">
              A number for the plan. Nothing is spent or sent to Meta from here.
            </span>
          </label>
        ) : null}
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={btnYel}
            disabled={!title.trim() || !due}
            onClick={() =>
              void save({ title: title.trim(), due, note, ...(item.kind === 'boost' ? { budget } : {}) })
            }
          >
            Save
          </button>
          <button type="button" className={btnQuiet} onClick={() => setEditing(false)}>
            Cancel
          </button>
          {err ? <span className="text-xs text-red">{err}</span> : null}
        </div>
      </li>
    )
  }

  return (
    <li
      className="flex flex-col gap-1 rounded-md bg-bg2 px-3 py-2 sm:flex-row sm:items-start sm:gap-3"
      data-testid="plan-item"
      data-kind={item.kind}
    >
      <div className="flex shrink-0 flex-wrap items-baseline gap-x-2 text-xs sm:block sm:w-28">
        <p className="font-semibold text-tx2">{formatPlanDate(item.due)}</p>
        <p className={item.late && !done ? 'text-red' : 'text-tx3'}>
          {done ? 'done' : item.late ? `late · ${dueLabel(item.due, today)}` : dueLabel(item.due, today)}
        </p>
      </div>
      <span className="w-14 shrink-0 self-start rounded bg-bg px-1.5 py-0.5 text-center text-[10px] font-bold tracking-wider text-tx2 uppercase sm:mt-0.5">
        {KIND_LABEL[item.kind]}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${done ? 'text-tx3 line-through' : 'text-tx'}`}>
          {item.title}
          {item.source === 'operator' ? (
            <span className="ml-2 text-[10px] font-bold tracking-wider text-ac uppercase">Yours</span>
          ) : null}
        </p>
        {item.note ? <p className="text-xs text-tx3">{item.note}</p> : null}
        {item.needs_real_video ? (
          <p className="text-[11px] text-tx3">Real video with a person on camera.</p>
        ) : null}
        {item.kind === 'boost' ? (
          <p className={`text-[11px] ${item.budget ? 'text-tx2' : 'text-yel'}`} data-testid="plan-budget-line">
            {item.budget ? `Planned budget ${formatRand(item.budget)}. Nothing is spent from here.` : 'No budget set yet.'}
          </p>
        ) : null}
        {err ? <p className="text-xs text-red">{err}</p> : null}
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-1 text-xs">
        {onCopyRequest ? (
          <button type="button" className={btnQuiet} onClick={onCopyRequest} data-testid="plan-step-copy-request">
            Copy request
          </button>
        ) : null}
        {locked ? (
          <button
            type="button"
            className={btnQuiet}
            onClick={() => void save({ status: done ? 'kept' : 'done' })}
          >
            {done ? 'Not done' : 'Mark done'}
          </button>
        ) : (
          <>
            <button type="button" className={btnQuiet} onClick={() => setEditing(true)}>
              Change
            </button>
            <button
              type="button"
              className={btnQuiet}
              onClick={() => void save({ status: 'removed' })}
            >
              Remove
            </button>
          </>
        )}
      </div>
    </li>
  )
}

function AddItem({ onAdd, eventDate }: { onAdd: (i: { title: string; due: string; kind: PlanItemKind }) => Promise<string | null>; eventDate: string }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [due, setDue] = useState(eventDate.slice(0, 10))
  const [kind, setKind] = useState<PlanItemKind>('post')
  const [err, setErr] = useState<string | null>(null)

  if (!open) {
    return (
      <button type="button" className={btnQuiet} onClick={() => setOpen(true)} data-testid="plan-add-open">
        + Add a step
      </button>
    )
  }
  return (
    <div className="space-y-2 rounded-md border border-bd bg-bg2 px-3 py-2" data-testid="plan-add-form">
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="What to do"
          placeholder="What needs doing?"
          className={`${field} min-w-0 flex-1`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input aria-label="Due date" type="date" className={field} value={due} onChange={(e) => setDue(e.target.value)} />
        <select
          aria-label="Type of step"
          className={field}
          value={kind}
          onChange={(e) => setKind(e.target.value as PlanItemKind)}
        >
          {KIND_ORDER.map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={btnYel}
          disabled={!title.trim() || !due}
          onClick={async () => {
            setErr(null)
            const e = await onAdd({ title: title.trim(), due, kind })
            if (e) setErr(e)
            else {
              setTitle('')
              setOpen(false)
            }
          }}
        >
          Add
        </button>
        <button type="button" className={btnQuiet} onClick={() => setOpen(false)}>
          Cancel
        </button>
        {err ? <span className="text-xs text-red">{err}</span> : null}
      </div>
    </div>
  )
}

/** The dated plan for one brief: make it, change it, approve it. Nothing here
 *  schedules or publishes; approving records the yes only. */
export function PlanPanel({ brandId, briefId }: { brandId: string; briefId: string }) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [composer, setComposer] = useState<{ kind: 'shoot'; stepIds: string[] } | { kind: 'signoff' } | null>(null)
  const today = todayIso()

  const take = useCallback((r: PlanResult): string | null => {
    if (r.ok && r.plan) {
      setPlan(r.plan)
      return null
    }
    return r.error || 'That did not work.'
  }, [])

  useEffect(() => {
    let cancelled = false
    void findPlan(brandId, briefId).then((r) => {
      if (cancelled) return
      if (r.ok) setPlan(r.plan || null)
      else setError(r.error || 'Could not load the plan.')
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [brandId, briefId])

  async function run(fn: () => Promise<PlanResult>) {
    setBusy(true)
    setError(null)
    const e = take(await fn())
    if (e) setError(e)
    else notifyAlertsChanged()
    setBusy(false)
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 px-3 py-4 text-sm text-tx3">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading the plan…
      </p>
    )
  }

  if (!plan) {
    return (
      <div className="space-y-2 px-3 py-4" data-testid="plan-empty">
        <p className="text-sm text-tx2">
          No plan yet. A plan lists what to check, shoot, approve and post, with a date on each step, counting
          back from the event.
        </p>
        <p className="text-xs text-tx3">Making a plan does not schedule or post anything. Approving it only records your yes for now.</p>
        <button
          type="button"
          className={btnYel}
          disabled={busy}
          onClick={() => void run(() => proposePlan(brandId, briefId))}
          data-testid="plan-make"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          {busy ? 'Making…' : 'Make a plan'}
        </button>
        {error ? <p className="text-xs text-red">{error}</p> : null}
      </div>
    )
  }

  const approved = plan.status === 'approved'
  const { active, removed } = splitItems(plan.items)
  const blocker = approveBlocker(plan)
  const boosts = boostBudget(plan.items)
  const late = active.filter((i) => i.late && i.status !== 'done').length

  return (
    <div className="space-y-3 px-3 py-4" data-testid="plan-panel">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-bold text-tx">
          {plan.event_name} · {formatPlanDate(plan.event_date)}
        </p>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider uppercase ${
            approved ? 'bg-emerald-500/15 text-emerald-400' : 'bg-yel/15 text-yel'
          }`}
        >
          {approved ? 'Approved' : 'Draft'}
        </span>
        <span className="text-xs text-tx3">
          {plan.placed_at
            ? 'On the calendar. Nothing is published until each post is approved and released.'
            : approved
              ? 'Approved, but not on the calendar yet.'
              : 'A draft. Change anything you like. Nothing is scheduled.'}
        </span>
      </div>

      {plan.profile_label ? (
        <p className="text-xs text-tx3" data-testid="plan-shape">
          <EventTypeIcon kind={plan.profile} size="sm" className="mr-1.5 align-middle" />
          Shaped as <b className="text-tx2">{plan.profile_label}</b>. {plan.profile_reason}
        </p>
      ) : null}

      {boosts.boosts ? (
        <p className="text-xs text-tx3" data-testid="plan-budget-total">
          Boost budget: <b className="text-tx2">{boosts.total ? formatRand(boosts.total) : 'none set'}</b>
          {boosts.missing && boosts.total
            ? ` (${boosts.missing} boost${boosts.missing === 1 ? ' has' : 's have'} no budget yet)`
            : ''}
          . A plan only, nothing is spent or sent to Meta from here.
        </p>
      ) : null}

      {late ? (
        <p className="rounded-md border border-red/30 bg-red/10 px-3 py-2 text-xs text-red" data-testid="plan-late">
          {late} {late === 1 ? 'step is' : 'steps are'} already past its date. They are marked in red, not moved.
          Change the dates or remove them.
        </p>
      ) : null}

      <ul className="space-y-1">
        {active.map((it) => (
          <ItemRow
            key={it.item_id}
            item={it}
            today={today}
            locked={approved}
            onSave={async (patch) => take(await editPlanItem(brandId, plan.plan_id, it.item_id, patch))}
            onCopyRequest={it.kind === 'shoot' ? () => setComposer({ kind: 'shoot', stepIds: [it.item_id] }) : undefined}
          />
        ))}
      </ul>

      {removed.length ? (
        <div className="space-y-1" data-testid="plan-removed">
          <p className="text-[11px] font-bold tracking-widest text-tx3 uppercase">Removed</p>
          {removed.map((it) => (
            <div key={it.item_id} className="flex items-center gap-3 px-3 text-xs text-tx3">
              <span className="line-through">{it.title}</span>
              {!approved ? (
                <button
                  type="button"
                  className="font-semibold text-yel hover:underline"
                  onClick={() => void run(() => editPlanItem(brandId, plan.plan_id, it.item_id, { status: 'kept' }))}
                >
                  Put back
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {!approved ? (
        <AddItem
          eventDate={plan.event_date}
          onAdd={async (i) => take(await addPlanItem(brandId, plan.plan_id, i))}
        />
      ) : null}

      <div className="flex flex-wrap items-center gap-2 border-t border-bd pt-3">
        {approved ? (
          <>
            {plan.placed_at ? (
              <button
                type="button"
                className={btnQuiet}
                disabled={busy}
                onClick={() => void run(() => unplacePlan(brandId, plan.plan_id))}
                data-testid="plan-unplace"
              >
                Take off the calendar (undo)
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className={btnYel}
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Put ${active.length} steps on the calendar? Dates only. Nothing is posted. You can undo this.`,
                      )
                    ) {
                      const name = actorName()
                      if (!name) {
                        setError('A name is needed so the calendar knows who booked these.')
                        return
                      }
                      void run(() => placePlan(brandId, plan.plan_id, name))
                    }
                  }}
                  data-testid="plan-place"
                >
                  {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                  Put on the calendar
                </button>
                <button
                  type="button"
                  className={btnQuiet}
                  disabled={busy}
                  onClick={() => void run(() => reopenPlan(brandId, plan.plan_id))}
                >
                  Reopen to edit
                </button>
              </>
            )}
          </>
        ) : (
          <>
            <button
              type="button"
              className={btnYel}
              disabled={busy || Boolean(blocker)}
              title={blocker || undefined}
              onClick={() => void run(() => approvePlan(brandId, plan.plan_id))}
              data-testid="plan-approve"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              Approve plan
            </button>
            <button
              type="button"
              className={btnQuiet}
              disabled={busy}
              onClick={() => {
                if (window.confirm('Start again with a fresh plan? Your changes to this one will be replaced.')) {
                  void run(() => proposePlan(brandId, briefId, true))
                }
              }}
            >
              Start again
            </button>
            <select
              aria-label="Change the shape of the plan"
              data-testid="plan-reshape"
              disabled={busy}
              value=""
              className={`${field} text-xs`}
              onChange={(e) => {
                const shape = e.target.value as PlanProfile
                if (!shape) return
                const label = PROFILE_OPTIONS.find((o) => o.id === shape)?.label || shape
                if (window.confirm(`Start again as a ${label}? Your changes to this plan will be replaced.`)) {
                  void run(() => proposePlan(brandId, briefId, true, shape))
                }
              }}
            >
              <option value="">Change the shape…</option>
              {PROFILE_OPTIONS.filter((o) => o.id !== plan.profile).map((o) => (
                <option key={o.id} value={o.id} title={o.hint}>
                  {o.label}: {o.hint}
                </option>
              ))}
            </select>
          </>
        )}
        {shootSteps(plan).length ? (
          <button
            type="button"
            className={btnQuiet}
            onClick={() => setComposer({ kind: 'shoot', stepIds: shootSteps(plan).map((i) => i.item_id) })}
            data-testid="plan-copy-shoot"
          >
            Copy shoot request
          </button>
        ) : null}
        <button
          type="button"
          className={btnQuiet}
          onClick={() => setComposer({ kind: 'signoff' })}
          data-testid="plan-copy-signoff"
        >
          Copy for sign-off
        </button>
        {!approved && blocker ? (
          <span className="text-xs text-tx3" data-testid="plan-blocker">
            {blocker}
          </span>
        ) : null}
        {error ? <span className="text-xs text-red">{error}</span> : null}
      </div>

      {composer?.kind === 'shoot' ? (
        <MessageComposer
          key={`shoot-${composer.stepIds.join(',')}`}
          title="Shoot request"
          intro="For whoever is shooting: the venue, the shop or the facility. Change anything, then copy it. Nothing is sent from here."
          fields={[
            { key: 'facility', label: 'Who is it for?', placeholder: 'e.g. Pieter' },
            { key: 'sendTo', label: 'Where should they send it?', placeholder: 'e.g. Christelle on WhatsApp', remember: true },
          ]}
          build={(v) =>
            shootRequest({
              plan,
              steps: plan.items.filter((i) => composer.stepIds.includes(i.item_id)),
              facility: v.facility,
              sendTo: v.sendTo,
              today,
            })
          }
          onClose={() => setComposer(null)}
        />
      ) : null}
      {composer?.kind === 'signoff' ? (
        <MessageComposer
          key="signoff"
          title="Plan for sign-off"
          intro="The whole plan, written out for someone to read and approve. Change anything, then copy it. Nothing is sent from here."
          fields={[{ key: 'to', label: 'Who is it for?', placeholder: 'e.g. Kyle' }]}
          build={(v) => signOffMessage({ plan, to: v.to, from: savedActorName(), today })}
          onClose={() => setComposer(null)}
        />
      ) : null}
    </div>
  )
}
