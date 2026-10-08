import { useEffect, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { brandDisplayName } from '../../../lib/planning'

// V2.9 §5+§6+§7+§10 — Operator Date Suggestion form.
//
// Submits via POST /api/calendar/candidates (the existing
// candidate-intake endpoint). The form sends a record with
// source=OPERATOR_PROVIDED, status=candidate, type=moment. The
// backend's V2.8 routing routes this to the candidate store
// (NOT the operator/Main Calendar). The suggestion never
// silently becomes approved. It surfaces in Candidates,
// then Christelle decides whether to Add to Main Calendar.

type Props = {
  brand: string
  brandId: string
  onClose: () => void
  onSubmitted: (result: { ok: boolean; record_id?: string; error?: string }) => void
  initialDate?: string // V2.11 — pre-fill the start date from the day cell the operator clicked
}

type SourceKind = 'OPERATOR' | 'CLIENT' | 'GOLF_CLUB' | 'WEBSITE' | 'OTHER'
type Importance = 'ASSESS' | 'A-PIN' | 'B-PIN' | 'C-PIN'
type EntryType = 'moment' | 'campaign'
type PillarOption = { pillar_id?: string; name?: string }

export function SuggestDateModal({ brand, brandId, onClose, onSubmitted, initialDate }: Props) {
  const [title, setTitle] = useState('')
  const [startDate, setStartDate] = useState(initialDate || '')
  const [endDate, setEndDate] = useState('')
  const [location, setLocation] = useState('')
  const [why, setWhy] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [sourceKind, setSourceKind] = useState<SourceKind>('OPERATOR')
  const [importance, setImportance] = useState<Importance>('ASSESS')
  const [notes, setNotes] = useState('')
  const [entryType, setEntryType] = useState<EntryType>('moment')
  const [pillar, setPillar] = useState('')
  const [pillarOptions, setPillarOptions] = useState<PillarOption[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetch(`/api/calendar/context/${encodeURIComponent(brandId)}`, { credentials: 'include' })
      .then((r) => r.json())
      .then((j: { pillars?: PillarOption[] }) => {
        if (live) setPillarOptions((j.pillars || []).filter((p) => p.pillar_id))
      })
      .catch(() => {
        if (live) setPillarOptions([])
      })
    return () => {
      live = false
    }
  }, [brandId])

  // A campaign needs a pillar: without one it can never get a Brief.
  const canSubmit =
    title.trim() && startDate && !submitting && (entryType !== 'campaign' || Boolean(pillar))

  const submit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const body: Record<string, unknown> = {
        brand_id: brandId,
        type: entryType,
        status: 'candidate',
        title: title.trim(),
        start: startDate,
        end: endDate || startDate,
        public_peak: startDate,
        source: 'OPERATOR_PROVIDED',
        source_kind: sourceKind.toLowerCase(),
        importance,
        notes: notes.trim(),
        created_by: 'operator',
        // Evidence is operator-supplied. Marked explicitly so the
        // React UI knows the suggestion has no external verification
        // yet (V2.9 §6).
        evidence_kind: 'OPERATOR_PROVIDED',
        is_suggested: true,
      }
      if (location.trim()) body.location = location.trim()
      if (sourceUrl.trim()) body.source_url = sourceUrl.trim()
      if (why.trim()) body.why_it_matters = why.trim()
      if (pillar) body.pillars = [pillar]

      const r = await fetch('/api/calendar/candidates', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const j = await r.json()
      if (r.ok && j.ok) {
        onSubmitted({ ok: true, record_id: j.record?.id || j.record?.calendar_id })
      } else {
        const errMsg = j.error || `HTTP ${r.status}`
        setError(errMsg)
        onSubmitted({ ok: false, error: errMsg })
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'submit failed'
      setError(msg)
      onSubmitted({ ok: false, error: msg })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Suggest a date for ${brandDisplayName(brand)}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-bd bg-bg2 p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold tracking-widest text-yel uppercase">Operator date</p>
            <h2 className="font-display text-2xl font-extrabold">+ Suggest Date</h2>
            <p className="mt-1 text-xs text-tx3">
              For {brandDisplayName(brand)}. Submits as a Candidate — never auto-approves.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="suggest-date-close"
            className="rounded-md p-1 text-tx2 hover:bg-white/5 hover:text-tx"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
          className="space-y-3"
          data-testid="suggest-date-form"
        >
          <label className="block">
            <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">Title *</span>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="suggest-title"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              placeholder="e.g. Ladies clinic at the Shack"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">Type</span>
              <select
                value={entryType}
                onChange={(e) => setEntryType(e.target.value as EntryType)}
                data-testid="suggest-type"
                className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              >
                <option value="moment">Moment (a date to note)</option>
                <option value="campaign">Campaign (can get a Brief)</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
                Pillar {entryType === 'campaign' ? '*' : <span className="text-tx3/60">(optional)</span>}
              </span>
              <select
                value={pillar}
                onChange={(e) => setPillar(e.target.value)}
                required={entryType === 'campaign'}
                data-testid="suggest-pillar"
                className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              >
                <option value="">{pillarOptions.length ? 'Choose a pillar' : 'No pillars set up'}</option>
                {pillarOptions.map((p) => (
                  <option key={p.pillar_id} value={p.pillar_id}>
                    {p.name || p.pillar_id}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
                Start date *
              </span>
              <input
                type="date"
                required
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                data-testid="suggest-start"
                className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
                End date <span className="text-tx3/60">(optional)</span>
              </span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                data-testid="suggest-end"
                className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              />
            </label>
          </div>

          <label className="block">
            <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">Brand *</span>
            <input
              type="text"
              readOnly
              value={brandDisplayName(brand)}
              data-testid="suggest-brand"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg/50 px-3 py-2 text-sm text-tx2"
            />
          </label>

          <label className="block">
            <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
              Location <span className="text-tx3/60">(optional)</span>
            </span>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              data-testid="suggest-location"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              placeholder="e.g. Randpark Golf Club, Johannesburg"
            />
          </label>

          <label className="block">
            <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
              Why does this matter?
            </span>
            <textarea
              value={why}
              onChange={(e) => setWhy(e.target.value)}
              data-testid="suggest-why"
              rows={2}
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              placeholder="e.g. Tailor-made clinic for our ladies' group — past attendance was strong."
            />
          </label>

          <label className="block">
            <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
              Source / URL <span className="text-tx3/60">(optional)</span>
            </span>
            <input
              type="text"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              data-testid="suggest-source-url"
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              placeholder="https://…"
            />
          </label>

          <fieldset>
            <legend className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
              How do I know about this?
            </legend>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(
                [
                  { id: 'OPERATOR', label: 'Operator knowledge' },
                  { id: 'CLIENT', label: 'Client/Herman' },
                  { id: 'GOLF_CLUB', label: 'Golf club' },
                  { id: 'WEBSITE', label: 'Website/source' },
                  { id: 'OTHER', label: 'Other' },
                ] as const
              ).map((opt) => (
                <label
                  key={opt.id}
                  className={`cursor-pointer rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                    sourceKind === opt.id
                      ? 'border-yel/60 bg-yel/15 text-yel'
                      : 'border-bd bg-bg2 text-tx2 hover:border-yel/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="source-kind"
                    value={opt.id}
                    checked={sourceKind === opt.id}
                    onChange={() => setSourceKind(opt.id)}
                    className="sr-only"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-[10px] font-bold tracking-wider text-tx3 uppercase">
              Suggested importance
            </legend>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(
                [
                  { id: 'ASSESS', label: 'Let Campaign OS assess' },
                  { id: 'A-PIN', label: 'A-PIN' },
                  { id: 'B-PIN', label: 'B-PIN' },
                  { id: 'C-PIN', label: 'C-PIN' },
                ] as const
              ).map((opt) => (
                <label
                  key={opt.id}
                  className={`cursor-pointer rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                    importance === opt.id
                      ? 'border-yel/60 bg-yel/15 text-yel'
                      : 'border-bd bg-bg2 text-tx2 hover:border-yel/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="importance"
                    value={opt.id}
                    checked={importance === opt.id}
                    onChange={() => setImportance(opt.id)}
                    className="sr-only"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </fieldset>

          <label className="block">
            <span className="text-[10px] font-bold tracking-wider text-tx3 uppercase">Notes</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="suggest-notes"
              rows={2}
              className="mt-1 w-full rounded-lg border border-white/10 bg-bg px-3 py-2 text-sm text-tx focus:border-yel/60 focus:outline-none"
              placeholder="Anything else the planner should know."
            />
          </label>

          {error ? (
            <p
              className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400"
              data-testid="suggest-error"
            >
              {error}
            </p>
          ) : null}

          <div className="flex items-center justify-between border-t border-bd pt-3">
            <p className="text-[10px] text-tx3">
              Submits as a <strong className="text-yel">Candidate</strong>. Human review required
              before any Main Calendar promotion.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-bd px-3 py-1.5 text-[11px] font-bold tracking-wider text-tx2 uppercase hover:border-yel/60 hover:text-yel"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!canSubmit}
                data-testid="suggest-submit"
                className="inline-flex items-center gap-1 rounded-md border border-yel/40 bg-yel/15 px-3 py-1.5 text-[11px] font-bold tracking-wider text-yel uppercase hover:bg-yel/25 disabled:opacity-50"
              >
                {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                {submitting ? 'Submitting…' : 'Submit'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
