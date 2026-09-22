import { ClipboardCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { FilterChips, PageIntro } from '../components/chrome'
import { Badge, Button, ClassicLink, StatCard, Tip } from '../components/ui'
import {
  fetchAccounts,
  fetchAgentQueue,
  fetchAgents,
  fetchJobsStatus,
  fetchLayers,
  type AccountItem,
  type AgentRow,
  type JobEntry,
  type LayerEntry,
  type QueueRow,
} from '../lib/api'
import { formatStamp } from '../lib/stamp'

type OpsTab = 'jobs' | 'agents' | 'accounts'

const TAB_OPTIONS = [
  { id: 'jobs', label: 'Jobs' },
  { id: 'agents', label: 'Agents' },
  { id: 'accounts', label: 'Accounts' },
]

function resolveTab(tab: string | null, layer: string | null): { tab: OpsTab; classicLayer: string | null } {
  if (tab === 'jobs' || tab === 'agents' || tab === 'accounts') {
    return { tab, classicLayer: null }
  }
  if (layer === 'agents') return { tab: 'agents', classicLayer: null }
  if (layer === 'jobs') return { tab: 'jobs', classicLayer: null }
  if (layer && !['jobs', 'agents'].includes(layer)) {
    return { tab: 'jobs', classicLayer: layer }
  }
  return { tab: 'jobs', classicLayer: null }
}

function verdictTone(verdict?: string | null): 'green' | 'gold' | 'red' | 'mute' {
  const v = (verdict || '').toUpperCase()
  if (v === 'OK') return 'green'
  if (v === 'LATE' || v === 'STUCK') return 'gold'
  if (v === 'FAILED') return 'red'
  return 'mute'
}

function agentStatusTone(agent: AgentRow): 'green' | 'gold' | 'red' | 'mute' {
  const v = (agent.last_status || '').toUpperCase()
  if (v === 'OK') return 'green'
  if (v === 'LATE') return 'gold'
  if (v === 'FAILED') return 'red'
  if (v === 'NEVER' && agent.enabled === false) return 'mute'
  if (v === 'NEVER') return 'mute'
  return 'mute'
}

function accountStateTone(state?: string): 'green' | 'gold' | 'red' | 'mute' | 'blue' {
  if (state === 'connected') return 'green'
  if (state === 'partial') return 'gold'
  if (state === 'missing') return 'red'
  if (state === 'na') return 'mute'
  return 'blue'
}

function SkeletonRows({ n = 4 }: { n?: number }) {
  return (
    <ul className="space-y-2">
      {Array.from({ length: n }).map((_, i) => (
        <li key={i} className="glass h-16 animate-pulse rounded-2xl border border-white/10" />
      ))}
    </ul>
  )
}

function jobRowMeta(job: JobEntry, brandId: string) {
  if (job.brand_mode === 'per_brand' && job.brands?.length) {
    const row = job.brands.find((b) => b.brand === brandId) || job.brands[0]
    if (row && row.applies === false) {
      return row.skipped_reason || 'Does not apply to this brand.'
    }
    if (row?.last_error) return row.last_error
    if (row?.last_status) return `Last status: ${row.last_status}`
  }
  if (job.last_error) return job.last_error
  return job.info || job.schedule || 'Scheduled job — check verdict.'
}

function jobVerdictForBrand(job: JobEntry, brandId: string) {
  if (job.brand_mode === 'per_brand' && job.brands?.length) {
    const row = job.brands.find((b) => b.brand === brandId)
    if (row?.verdict) return row.verdict
  }
  return job.verdict
}

function jobLastRunForBrand(job: JobEntry, brandId: string) {
  if (job.brand_mode === 'per_brand' && job.brands?.length) {
    const row = job.brands.find((b) => b.brand === brandId)
    if (row?.last_run_at) return row.last_run_at
  }
  return job.last_run_at
}

function LayerRibbon({
  layers,
  onSelectTab,
}: {
  layers: Record<string, LayerEntry> | undefined
  onSelectTab: (tab: OpsTab) => void
}) {
  if (!layers) return null
  const entries = Object.entries(layers)
  if (!entries.length) return null

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {entries.map(([key, layer]) => {
        const verdict = layer.verdict || '—'
        const tone = verdictTone(verdict)
        const layerKey = key.toLowerCase()
        const nativeTab: OpsTab | null =
          layerKey.includes('agent') ? 'agents' : layerKey.includes('job') ? 'jobs' : null
        const tip = nativeTab
          ? `Open native ${nativeTab} tab. ${layer.label || key}.`
          : `Layer ${layer.label || key} — open Classic for the full ribbon view.`
        if (nativeTab) {
          const openTip = `Show native ${nativeTab} tab for ${layer.label || key}.`
          return (
            <Tip key={key} text={openTip} block>
              <button
                type="button"
                title={openTip}
                onClick={() => onSelectTab(nativeTab)}
                className="w-full text-left"
              >
                <StatCard
                  icon={ClipboardCheck}
                  label={layer.label || key}
                  value={verdict}
                  hint={layer.pending != null ? `${layer.pending} pending` : 'Fleet layer'}
                  tone={tone === 'green' ? 'green' : tone === 'gold' ? 'gold' : 'mute'}
                />
              </button>
            </Tip>
          )
        }
        return (
          <Tip key={key} text={tip} block>
            <button
              type="button"
              title={tip}
              onClick={() => onSelectTab('jobs')}
              className="glass w-full rounded-2xl border-[1.5px] border-bd px-3 py-3 text-left backdrop-blur-xl"
            >
              <p className="text-[13px] font-semibold tracking-[0.14em] text-tx3 uppercase">
                {layer.label || key}
              </p>
              <p className="mt-1 font-display text-2xl font-semibold">{verdict}</p>
              <p className="mt-0.5 text-xs text-tx3">
                Classic only —{' '}
                <ClassicLink href={layer.href || `/ops?layer=${key}`} label={layer.label || key} />
              </p>
            </button>
          </Tip>
        )
      })}
    </div>
  )
}

function JobsTab({ brandId }: { brandId: string }) {
  const [jobs, setJobs] = useState<JobEntry[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setJobs(null)
    setErr(null)
    fetchJobsStatus()
      .then((res) => setJobs(res.jobs || []))
      .catch((e) => {
        setJobs([])
        setErr(e instanceof Error ? e.message : 'Could not load jobs.')
      })
  }, [])

  if (jobs === null) return <SkeletonRows n={6} />
  if (err) {
    return (
      <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">{err}</p>
    )
  }
  if (!jobs.length) {
    return (
      <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
        No jobs registered yet — check Classic or wait for the registry.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-tx2">
          Scheduled work for the fleet. Per-brand jobs follow the brand switch above.
        </p>
        <ClassicLink href="/ops?layer=jobs" label="Jobs" />
      </div>
      <ul className="space-y-2">
        {jobs.map((job) => {
          const name = job.name || 'job'
          const verdict = jobVerdictForBrand(job, brandId)
          const tone = verdictTone(verdict)
          const meta = jobRowMeta(job, brandId)
          const when = formatStamp(jobLastRunForBrand(job, brandId))
          return (
            <li
              key={name}
              className="glass rounded-2xl border-[1.5px] border-white/10 px-4 py-3 backdrop-blur-xl"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{name}</span>
                    <Badge tone={tone}>{verdict || 'NEVER'}</Badge>
                    {job.criticality ? (
                      <span className="text-[12px] font-semibold tracking-wide text-tx3 uppercase">
                        {job.criticality}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-tx2">{meta}</p>
                  <p className="mt-0.5 text-xs text-tx3">
                    {job.schedule ? `${job.schedule} · ` : ''}
                    Last run {when}
                  </p>
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function AgentsTab({ brandId, highlightAgent }: { brandId: string; highlightAgent: string | null }) {
  const [agents, setAgents] = useState<AgentRow[] | null>(null)
  const [queue, setQueue] = useState<QueueRow[] | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setAgents(null)
    setQueue(null)
    setErr(null)
    Promise.all([fetchAgents(), fetchAgentQueue({ brand: brandId, limit: 50 })])
      .then(([agentRes, queueRes]) => {
        setAgents(agentRes.agents || [])
        setQueue(queueRes.rows || [])
        setPending(queueRes.counts?.pending ?? 0)
      })
      .catch((e) => {
        setAgents([])
        setQueue([])
        setErr(e instanceof Error ? e.message : 'Could not load agents.')
      })
  }, [brandId])

  if (agents === null) return <SkeletonRows n={5} />

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-tx2">
          Agent roster is fleet-wide. The queue below is scoped to the active brand.
        </p>
        <ClassicLink href="/ops?layer=agents" label="Agents" />
      </div>
      {err ? (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-4 text-sm text-tx3">{err}</p>
      ) : null}
      <ul className="grid gap-3 md:grid-cols-2">
        {(agents || []).map((agent) => {
          const id = agent.id || 'agent'
          const on = highlightAgent === id
          const tone = agentStatusTone(agent)
          return (
            <li
              key={id}
              className={`glass rounded-2xl border-[1.5px] px-4 py-3 backdrop-blur-xl ${
                on ? 'border-yel/50 shadow-[0_0_0_2px_rgba(251,191,36,.15)]' : 'border-white/10'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{id}</span>
                <Badge tone={tone}>{agent.last_status || 'NEVER'}</Badge>
                {agent.enabled === false ? (
                  <span className="text-[12px] text-tx3">Cron off</span>
                ) : null}
              </div>
              <p className="mt-1 text-sm text-tx2">{agent.last_action || 'No heartbeat yet.'}</p>
              <dl className="mt-2 grid gap-1 text-xs text-tx3">
                <div>
                  <span className="text-tx2">Profile:</span> {agent.profile || '—'}
                </div>
                <div>
                  <span className="text-tx2">Kind:</span> {agent.kind || '—'} · {agent.layer || '—'}
                </div>
                <div>
                  <span className="text-tx2">Schedule:</span> {agent.schedule || '—'}
                </div>
                <div>
                  <span className="text-tx2">Last beat:</span>{' '}
                  {formatStamp(agent.last_heartbeat_at)}
                </div>
                <div>
                  <span className="text-tx2">Writes:</span>{' '}
                  {(agent.last_writes || []).join(', ') || '—'}
                </div>
                <div>
                  <span className="text-tx2">Skill:</span> {agent.skill || '—'}
                </div>
              </dl>
            </li>
          )
        })}
      </ul>

      <section>
        <h2 className="mb-2 font-display text-xl font-semibold">
          Agent queue
          {pending != null ? (
            <span className="ml-2 text-base font-normal text-tx3">({pending} pending)</span>
          ) : null}
        </h2>
        {queue === null ? (
          <SkeletonRows n={3} />
        ) : queue.length ? (
          <ul className="space-y-2">
            {queue.map((row) => (
              <li
                key={row.id || `${row.agent}-${row.action}`}
                className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={row.status === 'pending' ? 'gold' : 'mute'}>
                    {row.status || 'unknown'}
                  </Badge>
                  <span className="font-semibold">{row.agent}</span>
                  <span className="text-tx3">{row.brand}</span>
                </div>
                <p className="mt-1 text-tx2">{row.action}</p>
                {row.payload_ref ? (
                  <p className="mt-0.5 text-xs text-tx3">Ref: {row.payload_ref}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
            Queue is empty for this brand.
          </p>
        )}
      </section>
    </div>
  )
}

function AccountConnectButton({ item, brandId }: { item: AccountItem; brandId: string }) {
  const [busy, setBusy] = useState(false)
  const connect = item.connect || {}
  const label = connect.label || 'Connect'

  const handleMetaRefresh = useCallback(async () => {
    setBusy(true)
    try {
      await fetch('/api/meta/fetch', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand_id: brandId }),
      })
    } finally {
      setBusy(false)
    }
  }, [brandId])

  if (connect.type === 'none' || (!connect.url && connect.type !== 'action')) {
    return connect.label ? <span className="text-xs text-tx3">{connect.label}</span> : null
  }

  if (connect.type === 'action' && item.id === 'meta') {
    const tip = 'Pull the latest Meta and Instagram stats for this brand.'
    return (
      <Tip text={tip}>
        <button
          type="button"
          title={tip}
          disabled={busy}
          onClick={() => void handleMetaRefresh()}
          className="inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg disabled:opacity-60"
        >
          {busy ? 'Fetching…' : label}
        </button>
      </Tip>
    )
  }

  if (connect.url) {
    const tip = `Connect ${item.name || 'this channel'}. Opens OAuth or setup.`
    return (
      <Tip text={tip}>
        <a
          href={connect.url}
          title={tip}
          className="inline-flex items-center gap-1.5 rounded-full bg-yel px-3 py-1.5 text-xs font-semibold text-bg"
        >
          {label}
        </a>
      </Tip>
    )
  }

  return null
}

function AccountRow({ item, brandId }: { item: AccountItem; brandId: string }) {
  const openDefault = item.state === 'missing' || item.state === 'partial'
  const tone = accountStateTone(item.state)
  const last = item.last_used_at ? formatStamp(item.last_used_at) : 'Never'

  return (
    <details
      open={openDefault}
      className="glass group rounded-2xl border-[1.5px] border-white/10 backdrop-blur-xl"
    >
      <summary className="flex cursor-pointer list-none items-start gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="text-2xl" aria-hidden>
          {item.icon || '🔌'}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{item.name}</span>
            <Badge tone={tone}>{item.state || 'unknown'}</Badge>
          </span>
          <p className="mt-0.5 text-sm text-tx2">{item.purpose}</p>
          <p className="mt-0.5 text-xs text-tx3">Last use: {last}</p>
        </span>
      </summary>
      <div className="border-t border-white/10 px-4 py-3 text-sm">
        {item.na_reason ? <p className="text-tx3">{item.na_reason}</p> : null}
        {item.error ? <p className="text-red">{item.error}</p> : null}
        <div className="mt-2">
          <AccountConnectButton item={item} brandId={brandId} />
        </div>
        {item.setup?.steps?.length ? (
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs text-tx2">
            {item.setup.steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        ) : null}
      </div>
    </details>
  )
}

function AccountsTab({ brandId }: { brandId: string }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchAccounts>> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setData(null)
    setErr(null)
    fetchAccounts(brandId)
      .then(setData)
      .catch((e) => {
        setData(null)
        setErr(e instanceof Error ? e.message : 'Could not load accounts.')
      })
  }, [brandId])

  if (data === null && !err) return <SkeletonRows n={5} />
  if (err || (data && !data.ok)) {
    return (
      <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
        {err || data?.error || 'Accounts could not load.'}
      </p>
    )
  }

  const categories = data?.categories || []
  const flat = categories.flatMap((c) => c.items || [])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-tx2">
          Connected channels for <span className="font-semibold text-tx">{brandId}</span>. Switch
          brand in the header to compare.
        </p>
        <ClassicLink href="/connected-accounts" label="Accounts" />
      </div>
      {data?.last_check ? (
        <p className="text-xs text-tx3">Checked {formatStamp(data.last_check)}</p>
      ) : null}
      {!flat.length ? (
        <p className="rounded-2xl border border-dashed border-bd px-4 py-6 text-sm text-tx3">
          No integrations listed — open Classic to run the full catalog.
        </p>
      ) : (
        <ul className="space-y-2">
          {categories.map((cat) =>
            (cat.items || []).map((item) => (
              <li key={item.id || item.name}>
                <AccountRow item={item} brandId={brandId} />
              </li>
            )),
          )}
        </ul>
      )}
    </div>
  )
}

export function Ops() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? 'stick'
  const [params, setParams] = useSearchParams()
  const tabParam = params.get('tab')
  const layerParam = params.get('layer')
  const highlightAgent = params.get('agent')

  const { tab, classicLayer } = useMemo(
    () => resolveTab(tabParam, layerParam),
    [tabParam, layerParam],
  )

  const [layers, setLayers] = useState<Record<string, LayerEntry> | undefined>()

  useEffect(() => {
    fetchLayers()
      .then((res) => setLayers(res.layers))
      .catch(() => setLayers(undefined))
  }, [])

  const setTab = useCallback(
    (next: OpsTab) => {
      const p = new URLSearchParams(params)
      p.set('tab', next)
      p.delete('layer')
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  return (
    <div className="space-y-6">
      <PageIntro here="/ops" title="Ops">
        Jobs, agents, and connected accounts — native Heroes, same APIs as Classic. The fleet is
        shared; accounts and per-brand job rows follow the brand switch.
      </PageIntro>

      <LayerRibbon layers={layers} onSelectTab={setTab} />

      {classicLayer ? (
        <p className="glass rounded-2xl border border-white/10 px-4 py-3 text-sm text-tx2">
          Layer <span className="font-semibold">{classicLayer}</span> still lives on Classic.{' '}
          <ClassicLink href={`/ops?layer=${classicLayer}`} label={classicLayer} />
        </p>
      ) : null}

      <FilterChips value={tab} options={TAB_OPTIONS} onChange={(id) => setTab(id as OpsTab)} />

      {tab === 'jobs' ? <JobsTab brandId={scopeBrand} /> : null}
      {tab === 'agents' ? (
        <AgentsTab brandId={scopeBrand} highlightAgent={highlightAgent} />
      ) : null}
      {tab === 'accounts' ? <AccountsTab brandId={scopeBrand} /> : null}

      <div className="flex flex-wrap gap-2 pt-2">
        <Button
          href="/ops?layer=health"
          tone="ghost"
          tip="Open health and digest on the Classic ops ribbon."
        >
          Health (Classic)
        </Button>
        <Button href="/?page=ops" tone="ghost" tip="Open the ops runbook in Classic.">
          Runbook
        </Button>
      </div>
    </div>
  )
}
