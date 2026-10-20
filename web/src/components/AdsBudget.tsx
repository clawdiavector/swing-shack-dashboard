import { useEffect, useState } from 'react'
import { getJson, postJson } from '../lib/api'
import { Badge } from './ui'

// Monthly ad budget for one brand: where the month stands and a box to set the budget.
// GET/POST /api/meta/ads/<brand>/budget. Setting a budget changes nothing in Meta.

export type BudgetEval = {
  month?: string
  as_of?: string
  budget: number | null
  mtd_spend: number
  projected_total: number
  worst_case_total: number
  left: number | null
  safe_per_day: number | null
  daily_run_rate: number
  used_pct?: number
  status: 'NO_BUDGET' | 'OK' | 'WATCH' | 'AT_RISK' | 'OVER'
  headline: string
  days_left_after_today?: number
  complete?: boolean
}

type Tone = 'mute' | 'gold' | 'green' | 'blue' | 'red'
const TONE: Record<BudgetEval['status'], Tone> = { NO_BUDGET: 'mute', OK: 'green', WATCH: 'gold', AT_RISK: 'red', OVER: 'red' }
const LABEL: Record<BudgetEval['status'], string> = {
  NO_BUDGET: 'No budget set',
  OK: 'On track',
  WATCH: 'Watch',
  AT_RISK: 'Heading over',
  OVER: 'Over budget',
}

export function rand(n: number | null | undefined): string {
  return n == null ? '—' : `R${Math.round(n).toLocaleString('en-ZA')}`
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-bg2/80 p-3">
      <p className="text-xs uppercase tracking-wide text-tx2">{label}</p>
      <p className="mt-1 text-xl font-semibold text-tx">{value}</p>
      {sub ? <p className="text-xs text-tx3">{sub}</p> : null}
    </div>
  )
}

export function BudgetView({
  ev,
  input,
  saving,
  error,
  onInput,
  onSave,
}: {
  ev: BudgetEval | null
  input: string
  saving: boolean
  error: string | null
  onInput: (v: string) => void
  onSave: () => void
}) {
  const budget = ev?.budget ?? null
  const max = Math.max(budget ?? 0, ev?.projected_total ?? 0, ev?.mtd_spend ?? 0, 1)
  const pct = (n: number) => `${Math.min(100, (n / max) * 100)}%`
  return (
    <div className="space-y-3">
      {ev ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TONE[ev.status]}>{LABEL[ev.status]}</Badge>
            <p className="text-sm text-tx2">{ev.headline}</p>
          </div>
          {budget ? (
            <div
              className="relative h-3 w-full rounded bg-bg3"
              role="img"
              aria-label={`Spent ${rand(ev.mtd_spend)}, expected ${rand(ev.projected_total)}, budget ${rand(budget)}`}
            >
              <div className="absolute inset-y-0 left-0 rounded bg-ac/40" style={{ width: pct(ev.projected_total) }} />
              <div className="absolute inset-y-0 left-0 rounded bg-ac" style={{ width: pct(ev.mtd_spend) }} />
              <div className="absolute -top-1 -bottom-1 w-0.5 bg-yel" style={{ left: pct(budget) }} title="Budget" />
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Spent so far" value={rand(ev.mtd_spend)} sub={ev.used_pct != null ? `${ev.used_pct}% of budget` : undefined} />
            <Stat label="Expected by month end" value={rand(ev.projected_total)} sub={`worst case ${rand(ev.worst_case_total)}`} />
            <Stat label="Left in budget" value={rand(ev.left)} />
            <Stat
              label="Safe per day"
              value={rand(ev.safe_per_day)}
              sub={`ad sets are set to ${rand(ev.daily_run_rate)} a day`}
            />
          </div>
          {ev.complete === false ? (
            <p className="text-xs text-red">Part of this month's spend could not be read from Meta, so these numbers may be low.</p>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-tx2">
          The first reading of this month's spend arrives with the next ads brief. You can set the budget now.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-tx2" htmlFor="monthly-budget">
          Monthly budget (R)
        </label>
        <input
          id="monthly-budget"
          inputMode="decimal"
          value={input}
          onChange={(e) => onInput(e.target.value)}
          className="w-32 rounded-lg border border-white/15 bg-transparent px-2 py-1 text-sm text-tx"
        />
        <button
          type="button"
          disabled={saving}
          onClick={onSave}
          className="rounded-full border border-white/15 px-3 py-1 text-xs font-semibold text-tx hover:border-ac hover:text-ac disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save budget'}
        </button>
        {error ? <span className="text-xs text-red">{error}</span> : null}
      </div>
      <p className="text-xs text-tx3">Saving a budget changes nothing in Meta. It only sets the line this page and the daily brief warn against.</p>
    </div>
  )
}

export function AdsBudget({ brandId }: { brandId: string }) {
  const [ev, setEv] = useState<BudgetEval | null>(null)
  const [input, setInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEv(null)
    setInput('')
    setError(null)
    getJson<{ budget: BudgetEval | null; settings?: { monthly_budget?: number | null } }>(`/api/meta/ads/${brandId}/budget`)
      .then((r) => {
        setEv(r.budget)
        const b = r.settings?.monthly_budget
        setInput(b ? String(b) : '')
      })
      .catch((e: Error) => setError(e.message))
  }, [brandId])

  const save = () => {
    const n = Number(input.replace(/[^0-9.]/g, ''))
    if (!Number.isFinite(n) || n < 0) {
      setError('Type the budget as a number, for example 8000.')
      return
    }
    setSaving(true)
    setError(null)
    postJson<{ budget: BudgetEval | null }>(`/api/meta/ads/${brandId}/budget`, { monthly_budget: n })
      .then((r) => setEv(r.budget))
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false))
  }

  return <BudgetView ev={ev} input={input} saving={saving} error={error} onInput={setInput} onSave={save} />
}
