import { LineChart } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import {
  fetchIntelWeeklyReport,
  fetchWeeklyReportJson,
  shareWeeklyReport,
  snapshotWeeklyReport,
  type IntelWeeklyReport,
  type WeeklyReportJson,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'

type WeekTab = 'summary' | 'hooks' | 'failures' | 'agents'

const TAB_OPTIONS = [
  { id: 'summary', label: 'Summary' },
  { id: 'hooks', label: 'Hooks & CTAs' },
  { id: 'failures', label: 'Failures' },
  { id: 'agents', label: 'Agents' },
]

const actionBtn =
  'rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50'
const primaryBtn = 'rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg hover:bg-yel/90 disabled:opacity-50'
const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

function resolveTab(raw: string | null): WeekTab {
  if (raw === 'hooks' || raw === 'failures' || raw === 'agents') return raw
  return 'summary'
}

function SkeletonBars({ n = 4 }: { n?: number }) {
  return (
    <ul className="space-y-2">
      {Array.from({ length: n }, (_, i) => (
        <li key={i} className="h-14 animate-pulse rounded-2xl bg-bg3" />
      ))}
    </ul>
  )
}

function BrandShareConfirm({
  brandId,
  onConfirm,
  onCancel,
}: {
  brandId: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const [typed, setTyped] = useState('')
  return (
    <div className="rounded-2xl border border-red/40 bg-red/5 p-4 text-sm">
      <p className="font-semibold text-tx">Mint a public share link (live)</p>
      <p className="mt-2 text-tx2">
        Anyone with the link can read the export until it expires. Type{' '}
        <span className="font-mono text-yel">{brandId}</span> to confirm for this brand.
      </p>
      <input
        className={`${inputCls} mt-3`}
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        aria-label="Confirm brand id for share link"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={primaryBtn} disabled={typed !== brandId} onClick={onConfirm}>
          Mint link
        </button>
        <button type="button" className={actionBtn} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

function metricEntries(metrics: Record<string, unknown> | undefined) {
  if (!metrics || typeof metrics !== 'object') return []
  return Object.entries(metrics).filter(([, v]) => v != null && typeof v !== 'object')
}

function renderClaimList(items: unknown[] | undefined, empty: string) {
  if (!items?.length) {
    return <p className="text-sm text-tx3">{empty}</p>
  }
  return (
    <ul className="space-y-2">
      {items.map((item, i) => {
        if (typeof item === 'string') {
          return (
            <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm text-tx">
              {item}
            </li>
          )
        }
        if (item && typeof item === 'object' && 'claim' in item) {
          const row = item as { claim?: string; evidence?: string; source?: string; severity?: string }
          return (
            <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
              <p className="font-medium text-tx">
                {row.severity ? (
                  <span className="mr-2 rounded-full bg-red/20 px-2 py-0.5 text-xs uppercase text-red">
                    {row.severity}
                  </span>
                ) : null}
                {row.claim || '—'}
                {row.source ? (
                  <span className="ml-2 font-mono text-xs text-tx3">{row.source}</span>
                ) : null}
              </p>
              {row.evidence ? <p className="mt-1 text-tx2">{row.evidence}</p> : null}
            </li>
          )
        }
        return (
          <li key={i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm text-tx">
            {JSON.stringify(item)}
          </li>
        )
      })}
    </ul>
  )
}

function renderHookish(items: unknown[] | undefined, empty: string) {
  return renderClaimList(items, empty)
}

function renderInterpretationBlock(interpretation: NonNullable<IntelWeeklyReport['interpretation']>) {
  if (typeof interpretation === 'string') {
    return (
      <div className="rounded-2xl border border-white/10 bg-bg2/30 p-4 text-sm text-tx2 whitespace-pre-wrap">
        {interpretation}
      </div>
    )
  }
  const sources = Array.isArray(interpretation.sources_used)
    ? interpretation.sources_used.filter((s): s is string => typeof s === 'string')
    : []
  return (
    <div className="space-y-4 rounded-2xl border border-white/10 bg-bg2/30 p-4 text-sm text-tx2">
      {interpretation.headline_take ? (
        <blockquote className="border-l-2 border-yel pl-3 font-medium text-tx">
          <span className="text-tx3">Headline take: </span>
          {interpretation.headline_take}
        </blockquote>
      ) : null}
      {interpretation.whats_working?.length ? (
        <div>
          <h3 className="mb-2 font-semibold text-tx">What&apos;s working</h3>
          {renderClaimList(interpretation.whats_working as unknown[], 'Nothing flagged as working.')}
        </div>
      ) : null}
      {interpretation.whats_not?.length ? (
        <div>
          <h3 className="mb-2 font-semibold text-tx">What&apos;s not</h3>
          {renderClaimList(interpretation.whats_not as unknown[], 'No issues flagged.')}
        </div>
      ) : null}
      {interpretation.look_at?.length ? (
        <div>
          <h3 className="mb-2 font-semibold text-tx">What to look at</h3>
          {renderClaimList(interpretation.look_at as unknown[], 'No follow-ups listed.')}
        </div>
      ) : null}
      {sources.length ? (
        <p className="text-xs text-tx3">
          Sources read ({sources.length}):{' '}
          {sources.map((s) => (
            <span key={s} className="mr-1 inline-block rounded-full border border-white/10 px-2 py-0.5 font-mono">
              {s}
            </span>
          ))}
        </p>
      ) : null}
    </div>
  )
}

export function Week() {
  const { brandId: rawBrandId, brandLabel } = useBrand()
  const brandId: string = rawBrandId ?? 'swing-shack'
  const [params, setParams] = useSearchParams()
  const tab = resolveTab(params.get('tab'))
  const [brandJson, setBrandJson] = useState<WeeklyReportJson | null>(null)
  const [intel, setIntel] = useState<IntelWeeklyReport | null>(null)
  const [brandErr, setBrandErr] = useState('')
  const [intelErr, setIntelErr] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [sharePending, setSharePending] = useState(false)
  const [shareUrl, setShareUrl] = useState('')
  const [shareExpires, setShareExpires] = useState('')

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const reload = useCallback(() => {
    setBrandErr('')
    setIntelErr('')
    fetchWeeklyReportJson(brandId)
      .then(setBrandJson)
      .catch((e: Error) => {
        setBrandJson(null)
        setBrandErr(e.message || 'GET /api/weekly-report?format=json failed')
      })
    fetchIntelWeeklyReport()
      .then(setIntel)
      .catch((e: Error) => {
        setIntel(null)
        setIntelErr(e.message || 'GET /api/intel/weekly_report failed')
      })
  }, [brandId])

  useEffect(() => {
    reload()
  }, [reload])

  const loading = brandJson === null && intel === null && !brandErr && !intelErr
  const delegated =
    brandJson?.data_source_brand_id && brandJson.data_source_brand_id !== brandJson.brand_id
  const kpiStrip = useMemo(() => metricEntries(brandJson?.metrics), [brandJson])
  const reportsV1Ok = brandId === 'swing-shack' || brandId === 'stick'

  async function handleSnapshot() {
    if (!window.confirm('Archive this week to disk? (live)')) return
    setActionMsg('')
    try {
      const out = await snapshotWeeklyReport(brandId)
      setActionMsg(out.path ? `Snapshot saved: ${out.path}` : 'Snapshot saved.')
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Snapshot failed')
    }
  }

  async function handleShareConfirm() {
    setActionMsg('')
    try {
      const out = await shareWeeklyReport()
      if (out.share_url) {
        setShareUrl(out.share_url)
        setShareExpires(out.expires_at || '')
        setActionMsg('Share link minted — copy it before you leave this screen.')
      } else {
        setActionMsg(out.error || 'Share mint failed')
      }
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : 'Share mint failed')
    } finally {
      setSharePending(false)
    }
  }

  const headline = intel?.headline || intel?.window_label
  const kpis = intel?.headline_kpis

  return (
    <div className="space-y-6">
      <PageIntro icon={LineChart} here="/results/week" title="This week">
        Brand-true KPIs from <code className="text-xs">/api/weekly-report</code> plus portfolio-wide
        detail from <code className="text-xs">/api/intel/weekly_report</code> for {brandLabel || brandId}.
      </PageIntro>

      {loading ? <SkeletonBars n={5} /> : null}

      {brandErr ? <p className="text-sm text-red">{brandErr}</p> : null}
      {intelErr ? <p className="text-sm text-red">{intelErr}</p> : null}
      {actionMsg ? <p className="text-sm text-yel">{actionMsg}</p> : null}

      {brandJson ? (
        <section className="glass rounded-2xl border border-ac/20 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Brand KPIs</h2>
            {delegated ? (
              <Badge tone="gold">Numbers delegated from {String(brandJson.data_source_brand_id)}</Badge>
            ) : null}
          </div>
          {kpiStrip.length ? (
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {kpiStrip.slice(0, 8).map(([key, val]) => (
                <div key={key} className="rounded-xl border border-white/10 px-3 py-2">
                  <p className="text-xs uppercase tracking-wide text-tx3">{key.replace(/_/g, ' ')}</p>
                  <p className="font-display text-xl font-semibold text-tx">{String(val)}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm text-tx3">No metrics yet — run the weekly pipeline or open Classic.</p>
          )}
        </section>
      ) : null}

      <p className="rounded-2xl border border-bd/60 bg-bg2/40 px-4 py-3 text-sm text-tx2">
        <span className="font-semibold text-tx">Portfolio-wide</span> — tabs below use{' '}
        <code className="text-xs">/api/intel/weekly_report</code>, which is not scoped to the brand chip.
        {intel?.window_note ? ` ${intel.window_note}` : ''}
      </p>

      {intel?.ts ? (
        <p className="text-xs text-tx3">Intel report as of {formatStamp(intel.ts)}</p>
      ) : null}

      <FilterChips options={TAB_OPTIONS} value={tab} onChange={setTab} />

      {tab === 'summary' && intel ? (
        <div className="space-y-4">
          {headline ? <p className="text-lg font-medium text-tx">{headline}</p> : null}
          {kpis ? (
            <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {Object.entries(kpis).map(([k, v]) => (
                <div key={k} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
                  <span className="text-tx3">{k.replace(/_/g, ' ')}</span>
                  <p className="font-semibold text-tx">{String(v ?? '—')}</p>
                </div>
              ))}
            </div>
          ) : null}
          {intel.interpretation ? renderInterpretationBlock(intel.interpretation) : null}
          {intel.week_on_week && Object.keys(intel.week_on_week).length ? (
            <div>
              <h3 className="mb-2 text-sm font-semibold text-tx">Week on week</h3>
              <ul className="space-y-1 text-sm text-tx2">
                {Object.entries(intel.week_on_week).map(([key, cell]) => (
                  <li key={key}>
                    {key}: {cell.current ?? '—'} vs {cell.previous ?? '—'}
                    {cell.pct_change != null ? ` (${cell.pct_change > 0 ? '+' : ''}${cell.pct_change}%)` : ''}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'hooks' && intel ? (
        <div className="space-y-6">
          <div>
            <h3 className="mb-2 font-semibold text-tx">Top hooks</h3>
            {renderHookish(intel.top_hooks as unknown[] | undefined, 'No hooks ranked this window yet.')}
          </div>
          <div>
            <h3 className="mb-2 font-semibold text-tx">Top CTAs</h3>
            {renderHookish(intel.top_ctas as unknown[] | undefined, 'No CTA rankings yet.')}
          </div>
          <div>
            <h3 className="mb-2 font-semibold text-tx">SEO movers</h3>
            {renderHookish(intel.seo_movers as unknown[] | undefined, 'No SEO movers in this report.')}
          </div>
        </div>
      ) : null}

      {tab === 'failures' && intel ? (
        <ul className="space-y-2">
          {(intel.failures || []).map((f, i) => (
            <li key={f.item_id || i} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
              <p className="font-medium text-tx">{f.platform || 'unknown'} — {f.reason || 'Failed'}</p>
              {f.ts ? <p className="mt-1 text-xs text-tx3">{formatStamp(f.ts)}</p> : null}
            </li>
          ))}
          {!intel.failures?.length ? (
            <li className="rounded-2xl border border-dashed border-bd px-4 py-8 text-sm text-tx3">
              No publish failures this window — check the publish queue if something stuck.
            </li>
          ) : null}
        </ul>
      ) : null}

      {tab === 'agents' && intel ? (
        <div className="space-y-4">
          {intel.agent_breakdown && Object.keys(intel.agent_breakdown).length ? (
            <ul className="space-y-2">
              {Object.entries(intel.agent_breakdown).map(([id, row]) => (
                <li key={id} className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm">
                  <p className="font-semibold text-tx">{id}</p>
                  <p className="text-tx2">
                    {row.passed ?? 0}/{row.total ?? 0} passed
                    {row.pass_rate_pct != null ? ` · ${row.pass_rate_pct}%` : ''}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-tx3">No agent runs recorded this week.</p>
          )}
        </div>
      ) : null}

      <section className="flex flex-wrap gap-2">
        <Tip text="Download markdown export (authed).">
          <a
            href="/api/intel/weekly_report/export"
            className={actionBtn}
            download
          >
            Export markdown
          </a>
        </Tip>
        <Tip text="Archive current week to disk (live).">
          <button type="button" className={actionBtn} onClick={handleSnapshot}>
            Snapshot week (live)
          </button>
        </Tip>
        <Tip text="Mint a no-login share URL (live, typed confirm).">
          <button type="button" className={actionBtn} onClick={() => setSharePending(true)}>
            Share link…
          </button>
        </Tip>
        {reportsV1Ok ? (
          <a href={`/api/reports/v1/${encodeURIComponent(brandId)}?format=html`} className={actionBtn}>
            Reporting intelligence V1
          </a>
        ) : (
          <span className={`${actionBtn} cursor-not-allowed opacity-50`} title="Only swing-shack and stick">
            Reporting V1 (not available for {brandId})
          </span>
        )}
      </section>

      {sharePending ? (
        <BrandShareConfirm
          brandId={brandId}
          onConfirm={handleShareConfirm}
          onCancel={() => setSharePending(false)}
        />
      ) : null}

      {shareUrl ? (
        <div className="rounded-2xl border border-yel/30 bg-bg2/40 p-4 text-sm">
          <p className="font-semibold text-tx">Copy share link</p>
          {shareExpires ? <p className="mt-1 text-xs text-tx3">Expires {formatStamp(shareExpires)}</p> : null}
          <input className={`${inputCls} mt-2 font-mono text-xs`} readOnly value={shareUrl} aria-label="Share URL" />
        </div>
      ) : null}

      <ClassicLink href="/weekly-report" label="public weekly report page" />
    </div>
  )
}
