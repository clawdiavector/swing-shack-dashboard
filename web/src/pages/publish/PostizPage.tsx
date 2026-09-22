import { Rocket } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageIntro } from '../../components/chrome'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import {
  fetchPostizChannels,
  fetchPostizStatus,
  fetchPublishMode,
  fetchPublishSandboxSummary,
  type PostizChannels,
  type PostizStatus,
  type PublishMode,
} from '../../lib/api'
import { formatStamp } from '../../lib/stamp'

function verdictFromOk(ok?: boolean, httpStatus?: number): 'green' | 'gold' | 'red' | 'mute' {
  if (httpStatus === 503) return 'gold'
  if (httpStatus === 502) return 'red'
  if (ok) return 'green'
  return 'mute'
}

export function PostizPage() {
  const [status, setStatus] = useState<(PostizStatus & { httpStatus?: number }) | null>(null)
  const [channels, setChannels] = useState<(PostizChannels & { httpStatus?: number }) | null>(null)
  const [channelsLoaded, setChannelsLoaded] = useState(false)
  const [mode, setMode] = useState<PublishMode | null>(null)
  const [sandbox, setSandbox] = useState<{ queue_depth?: number; receipt_count?: number } | null>(null)

  useEffect(() => {
    fetchPostizStatus().then(setStatus).catch(() => setStatus({ ok: false, error: 'Could not load status' }))
    fetchPublishMode()
      .then(setMode)
      .catch(() => setMode(null))
    fetchPublishSandboxSummary()
      .then(setSandbox)
      .catch(() => setSandbox(null))
  }, [])

  useEffect(() => {
    if (channelsLoaded) return
    setChannelsLoaded(true)
    fetchPostizChannels()
      .then(setChannels)
      .catch(() => setChannels({ ok: false, error: 'Could not load channels' }))
  }, [channelsLoaded])

  const modeLabel =
    mode?.mode === 'live'
      ? 'Live dispatch mode'
      : 'Sandbox — applies to the dispatch job only, not buttons on this page'

  return (
    <div className="space-y-6">
      <PageIntro icon={Rocket} here="/publish/postiz" title="Postiz">
        Credentials and connected channels. Connect OAuth on{' '}
        <Link to="/ops?tab=accounts" className="text-ac underline">
          Accounts
        </Link>
        .
      </PageIntro>

      <p className="rounded-2xl border border-yel/30 bg-yel/5 px-4 py-3 text-sm text-tx2">
        <span className="font-semibold text-yel">{mode?.label || 'Mode'}</span> — {modeLabel}
        {sandbox?.queue_depth != null ? (
          <span className="mt-1 block text-xs text-tx3">
            Sandbox queue depth {sandbox.queue_depth}, receipts {sandbox.receipt_count ?? 0}
          </span>
        ) : null}
      </p>

      <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
        <h2 className="font-display text-lg font-semibold">Credentials</h2>
        {!status ? (
          <p className="text-sm text-tx3">Loading…</p>
        ) : (
          <>
            <p className="flex flex-wrap items-center gap-2 text-sm">
              API key{' '}
              <Badge tone={status.api_key_present ? 'green' : 'red'}>
                {status.api_key_present ? 'configured ✓' : 'not configured ✗'}
              </Badge>
              OAuth client id{' '}
              <Badge tone={status.oauth_client_id_present ? 'green' : 'mute'}>
                {status.oauth_client_id_present ? 'present ✓' : 'missing ✗'}
              </Badge>
              OAuth client secret{' '}
              <Badge tone={status.oauth_client_secret_present ? 'green' : 'mute'}>
                {status.oauth_client_secret_present ? 'present ✓' : 'missing ✗'}
              </Badge>
            </p>
            {status.api_base ? <p className="text-xs text-tx3">API base: {status.api_base}</p> : null}
            {status.last_check ? (
              <p className="text-xs text-tx3">Last check: {formatStamp(status.last_check)}</p>
            ) : null}
            {status.error ? <p className="text-sm text-red">{status.error}</p> : null}
            <Badge tone={verdictFromOk(status.ok, status.httpStatus)}>
              {status.httpStatus === 503 ? 'Postiz client unavailable' : status.ok ? 'OK' : 'Check config'}
            </Badge>
            {(status.oauth_token_brands || []).length ? (
              <ul className="mt-3 space-y-2 text-xs text-tx2">
                {status.oauth_token_brands!.map((row, i) => (
                  <li key={i} className="rounded-xl border border-white/5 px-3 py-2">
                    Brand {String(row.brand_id || '—')} · scope {String(row.scope || '—')} · rotated{' '}
                    {row.rotated_at ? formatStamp(String(row.rotated_at)) : '—'} · access{' '}
                    {row.has_access_token ? '✓' : '✗'} · refresh {row.has_refresh_token ? '✓' : '✗'}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        )}
      </section>

      <section className="glass space-y-3 rounded-2xl border border-white/10 p-4">
        <h2 className="font-display text-lg font-semibold">Channels</h2>
        <Tip text="Fetched from Postiz on demand (60s server cache).">
          <p className="text-xs text-tx3">Loaded once when you open this page.</p>
        </Tip>
        {!channels ? (
          <p className="text-sm text-tx3">Loading channels…</p>
        ) : channels.httpStatus === 503 ? (
          <p className="text-sm text-yel">No API key — channels not available.</p>
        ) : channels.httpStatus === 502 ? (
          <p className="text-sm text-red">{channels.error || 'Postiz returned an error.'}</p>
        ) : !channels.channels?.length ? (
          <p className="text-sm text-tx3">Zero channels connected in Postiz.</p>
        ) : (
          <ul className="space-y-2">
            {channels.channels.map((ch) => (
              <li
                key={String(ch.id)}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/5 px-3 py-2 text-sm"
              >
                <span>
                  {ch.name || '—'} · {ch.provider || 'provider'}
                </span>
                {ch.disabled ? <Badge tone="gold">disabled</Badge> : <Badge tone="green">active</Badge>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ClassicLink href="/?page=postiz" label="Postiz" />
    </div>
  )
}
