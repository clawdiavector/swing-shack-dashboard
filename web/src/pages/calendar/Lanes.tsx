import { Map } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../../components/chrome'
import { ClassicLink } from '../../components/ui'
import {
  fetchImportantDates,
  fetchPlanningBigIdea,
  fetchPlanningMonth,
  fetchPlanningRightNow,
  fetchPlanningTimeline,
} from '../../lib/api'

type LanesTab = 'now' | 'month' | 'timeline'

const TAB_OPTIONS = [
  { id: 'now', label: 'Right now' },
  { id: 'month', label: 'Month' },
  { id: 'timeline', label: 'Timeline' },
]

async function safeLoad<T>(fn: () => Promise<T>): Promise<T | { ok: false }> {
  try {
    return await fn()
  } catch {
    return { ok: false }
  }
}

function panelFailed(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object') return true
  const o = payload as { ok?: boolean; error?: string }
  return o.ok === false
}

export function Lanes() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as LanesTab) || 'now'
  const monthParam =
    params.get('month') ||
    `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
  const yearParam = params.get('year') || String(new Date().getFullYear())

  const [bigIdea, setBigIdea] = useState<Record<string, unknown> | null>(null)
  const [rightNow, setRightNow] = useState<Record<string, unknown> | null>(null)
  const [monthView, setMonthView] = useState<Record<string, unknown> | null>(null)
  const [timeline, setTimeline] = useState<Record<string, unknown> | null>(null)
  const [important, setImportant] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  useEffect(() => {
    if (!scopeBrand) return
    let gone = false
    setLoading(true)
    Promise.all([
      safeLoad(() => fetchPlanningBigIdea(scopeBrand)),
      safeLoad(() => fetchPlanningRightNow(scopeBrand)),
      safeLoad(() => fetchPlanningMonth(scopeBrand, monthParam)),
      safeLoad(() => fetchPlanningTimeline(scopeBrand, yearParam)),
      safeLoad(() => fetchImportantDates(yearParam)),
    ]).then(([bi, rn, mo, tl, imp]) => {
      if (gone) return
      setBigIdea(bi as Record<string, unknown>)
      setRightNow(rn as Record<string, unknown>)
      setMonthView(mo as Record<string, unknown>)
      setTimeline(tl as Record<string, unknown>)
      setImportant(imp as Record<string, unknown>)
      setLoading(false)
    })
    return () => {
      gone = true
    }
  }, [scopeBrand, monthParam, yearParam])

  const brandLabel = scopeBrand || 'brand'

  const monthTheme = useMemo(() => {
    if (!monthView || panelFailed(monthView)) return ''
    return String((monthView as { monthly_theme?: string }).monthly_theme || '')
  }, [monthView])

  const runwayNote = useMemo(() => {
    if (!monthView || panelFailed(monthView)) return ''
    return String((monthView as { production_runway_note?: string }).production_runway_note || '')
  }, [monthView])

  const reminder = useMemo(() => {
    if (!monthView || panelFailed(monthView)) return ''
    return String((monthView as { reminder?: string }).reminder || '')
  }, [monthView])

  return (
    <div className="space-y-6">
      <PageIntro icon={Map} badge="Lanes" here="/calendar" title="Planning">
        Themes, lanes, and runway — same brand as the rest of Heroes.
      </PageIntro>

      <HeroPanel icon={Map} kicker="Big idea" title={scopeBrand ? `Lanes · ${scopeBrand}` : 'Pick a brand'}>
        {panelFailed(bigIdea) ? (
          <p className="text-sm text-tx3">No planning data for {brandLabel}.</p>
        ) : (
          <p className="text-sm text-tx">
            {String((bigIdea as { big_brand_idea?: string })?.big_brand_idea || (bigIdea as { idea?: string })?.idea || '—')}
          </p>
        )}
        <ClassicLink href="/?page=planning" label="planning" />
      </HeroPanel>

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />

      {loading ? <p className="text-sm text-tx3">Loading lanes…</p> : null}

      {tab === 'now' ? (
        <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
          <h2 className="font-display text-lg font-semibold">Right now</h2>
          {panelFailed(rightNow) ? (
            <p className="text-sm text-tx3">No right-now data for {brandLabel}.</p>
          ) : (
            <>
              <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-tx2">
                {JSON.stringify(
                  {
                    lanes: (rightNow as { active_lanes?: unknown }).active_lanes,
                    deadlines: (rightNow as { upcoming_deadlines?: unknown }).upcoming_deadlines,
                    next_major: (rightNow as { next_major?: unknown }).next_major,
                  },
                  null,
                  2,
                )}
              </pre>
            </>
          )}
        </section>
      ) : null}

      {tab === 'month' ? (
        <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
          <h2 className="font-display text-lg font-semibold">Month · {monthParam}</h2>
          <label className="flex items-center gap-2 text-sm text-tx2">
            Month
            <input
              type="month"
              value={monthParam}
              onChange={(e) => {
                const p = new URLSearchParams(params)
                p.set('month', e.target.value)
                p.set('tab', 'month')
                setParams(p, { replace: true })
              }}
              className="rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx"
            />
          </label>
          {panelFailed(monthView) ? (
            <p className="text-sm text-tx3">No month plan for {brandLabel}.</p>
          ) : (
            <>
              {monthTheme ? <p className="text-sm font-semibold text-yel">{monthTheme}</p> : null}
              {runwayNote ? (
                <p className="text-sm text-tx2">
                  <span className="font-semibold text-tx">Runway:</span> {runwayNote}
                </p>
              ) : null}
              {reminder ? (
                <p className="text-sm text-tx2">
                  <span className="font-semibold text-tx">Reminder:</span> {reminder}
                </p>
              ) : null}
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs text-tx3">
                {JSON.stringify(
                  {
                    lane_system: (monthView as { lane_system?: unknown }).lane_system,
                    active_campaigns: (monthView as { active_campaigns?: unknown }).active_campaigns,
                    important_dates: (monthView as { important_dates?: unknown }).important_dates,
                    days: (monthView as { days?: unknown }).days,
                  },
                  null,
                  2,
                )}
              </pre>
            </>
          )}
        </section>
      ) : null}

      {tab === 'timeline' ? (
        <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
          <h2 className="font-display text-lg font-semibold">Timeline · {yearParam}</h2>
          <label className="flex items-center gap-2 text-sm text-tx2">
            Year
            <input
              type="number"
              min={2020}
              max={2035}
              value={yearParam}
              onChange={(e) => {
                const p = new URLSearchParams(params)
                p.set('year', e.target.value)
                p.set('tab', 'timeline')
                setParams(p, { replace: true })
              }}
              className="w-24 rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx"
            />
          </label>
          {panelFailed(timeline) && panelFailed(important) ? (
            <p className="text-sm text-tx3">No timeline for {brandLabel}.</p>
          ) : (
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs text-tx3">
              {JSON.stringify({ timeline, important_dates: important }, null, 2)}
            </pre>
          )}
        </section>
      ) : null}
    </div>
  )
}
