import { Lightbulb, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../../components/chrome'
import { ClassicLink, Tip } from '../../components/ui'
import {
  addCalendarCandidate,
  fetchOpportunities,
  generateIdeas,
  type OpportunitiesPayload,
} from '../../lib/api'
import { isoDate, parseIsoDateParam } from '../../lib/stamp'

type IdeasTab = 'ideas' | 'today' | 'week' | 'missed' | 'upsells' | 'bundles' | 'leaks'

const TAB_OPTIONS = [
  { id: 'ideas', label: 'Ideas' },
  { id: 'today', label: 'Today' },
  { id: 'week', label: 'This week' },
  { id: 'missed', label: 'Missed' },
  { id: 'upsells', label: 'Upsells' },
  { id: 'bundles', label: 'Bundles' },
  { id: 'leaks', label: 'Leaks' },
]

function ideaTitle(row: unknown): string {
  if (typeof row === 'string') return row
  if (row && typeof row === 'object') {
    const o = row as Record<string, unknown>
    return String(o.title || o.name || o.idea || o.hook || o.headline || 'Untitled')
  }
  return 'Untitled'
}

function ideaHint(row: unknown): string {
  if (!row || typeof row !== 'object') return ''
  const o = row as Record<string, unknown>
  return String(o.angle || o.why || o.rationale || o.summary || o.pillar || '')
}

function bucketForTab(tab: IdeasTab, data: OpportunitiesPayload | null): unknown[] {
  if (!data) return []
  switch (tab) {
    case 'ideas':
      return data.ideas || []
    case 'today':
      return data.post_today || []
    case 'week':
      return data.this_week || []
    case 'missed':
      return data.missed || []
    case 'upsells':
      return data.upsells || []
    case 'bundles':
      return data.bundles || []
    case 'leaks':
      return data.funnel_leaks || []
    default:
      return []
  }
}

export function Ideas() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as IdeasTab) || 'ideas'
  const parkDate = useMemo(() => parseIsoDateParam(params.get('date')), [params])
  const parkIso = isoDate(parkDate)
  const [data, setData] = useState<OpportunitiesPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [genBusy, setGenBusy] = useState(false)
  const [parkMsg, setParkMsg] = useState('')
  const [parkBusy, setParkBusy] = useState<string | null>(null)

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const setParkDateIso = useCallback(
    (nextIso: string) => {
      const p = new URLSearchParams(params)
      p.set('date', nextIso)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  useEffect(() => {
    if (!scopeBrand) return
    let gone = false
    setLoading(true)
    fetchOpportunities(scopeBrand)
      .then((payload) => {
        if (!gone) setData(payload)
      })
      .catch(() => {
        if (!gone) setData(null)
      })
      .finally(() => {
        if (!gone) setLoading(false)
      })
    return () => {
      gone = true
    }
  }, [scopeBrand])

  const rows = useMemo(() => bucketForTab(tab, data), [tab, data])
  const parkLabel = parkDate.toLocaleDateString('en-ZA', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  const handleGenerate = async () => {
    if (!scopeBrand) return
    setGenBusy(true)
    try {
      await generateIdeas(scopeBrand, 6, 'instagram')
      const fresh = await fetchOpportunities(scopeBrand)
      setData(fresh)
    } catch {
      /* ignore */
    } finally {
      setGenBusy(false)
    }
  }

  const handlePark = async (title: string) => {
    if (!scopeBrand || !title.trim()) return
    setParkBusy(title)
    setParkMsg('')
    try {
      const res = await addCalendarCandidate({
        brand_id: scopeBrand,
        type: 'content',
        title: title.trim(),
        event_date: parkIso,
        source_type: 'operator',
      })
      if (res.ok) {
        setParkMsg(`Parked on ${parkLabel}.`)
      } else {
        setParkMsg(res.error || 'Could not park.')
      }
    } catch (e) {
      setParkMsg(e instanceof Error ? e.message : 'Could not park.')
    } finally {
      setParkBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro icon={Lightbulb} badge="Backlog" here="/calendar" title="Ideas">
        Park an idea onto a day — it lands on the calendar grid.
      </PageIntro>

      <HeroPanel
        icon={Lightbulb}
        kicker="Park target"
        title={`Parking to ${parkLabel}`}
        meta="Change the date below or pick one on Calendar first."
      >
        <label className="flex flex-wrap items-center gap-2 text-sm text-tx2">
          <span>Date</span>
          <input
            type="date"
            value={parkIso}
            onChange={(e) => setParkDateIso(e.target.value || isoDate(new Date()))}
            className="rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx"
          />
        </label>
        <Tip text="Generate six fresh ideas from intel.">
          <button
            type="button"
            disabled={genBusy || !scopeBrand}
            onClick={handleGenerate}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-tx hover:border-ac"
          >
            <Sparkles className="h-4 w-4" strokeWidth={2.5} />
            {genBusy ? 'Generating…' : 'Generate ideas'}
          </button>
        </Tip>
        <ClassicLink href="/?page=ideas" label="ideas" />
      </HeroPanel>

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />

      {parkMsg ? (
        <p className="text-sm text-ac">
          {parkMsg}{' '}
          <Link to={`/calendar?date=${encodeURIComponent(parkIso)}`} className="font-semibold text-yel">
            View on calendar
          </Link>
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-tx3">Loading ideas…</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row, i) => {
            const title = ideaTitle(row)
            const hint = ideaHint(row)
            const busy = parkBusy === title
            return (
              <li
                key={`${tab}-${i}-${title.slice(0, 24)}`}
                className="glass rounded-2xl border border-white/10 p-4 backdrop-blur-xl"
              >
                <p className="font-semibold text-tx">{title}</p>
                {hint ? <p className="mt-1 text-sm text-tx3">{hint}</p> : null}
                <div className="mt-3">
                  <Tip text={`Park this idea on ${parkLabel}.`}>
                    <button
                      type="button"
                      disabled={busy || !scopeBrand}
                      onClick={() => handlePark(title)}
                      className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
                    >
                      {busy ? 'Parking…' : `Park on ${parkLabel}`}
                    </button>
                  </Tip>
                </div>
              </li>
            )
          })}
          {!rows.length ? (
            <li className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
              Nothing in this bucket yet. Try Generate or another tab.
            </li>
          ) : null}
        </ul>
      )}
    </div>
  )
}
