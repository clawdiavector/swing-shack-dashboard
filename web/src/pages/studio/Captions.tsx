import { MessageSquareText } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useBrand } from '../../components/BrandSwitch'
import { HeroPanel, PageIntro } from '../../components/chrome'
import { Badge, ClassicLink, Tip } from '../../components/ui'
import { getJson, postJson } from '../../lib/api'

type Survivor = {
  id?: string
  caption?: string
  route?: string
  mechanism?: string
  checks?: { name?: string; passed?: boolean }[]
}

type GenerateResponse = {
  ok?: boolean
  survivors?: Survivor[]
  rejects_by_check?: Record<string, unknown[]>
  error?: string
}

type SavedCaption = { id?: string; caption?: string; created_at?: string }

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

export function Captions() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [brief, setBrief] = useState('')
  const [survivors, setSurvivors] = useState<Survivor[]>([])
  const [rejects, setRejects] = useState<Record<string, unknown[]> | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [voiceBible, setVoiceBible] = useState<unknown>(null)
  const [saved, setSaved] = useState<SavedCaption[]>([])
  const [showRejects, setShowRejects] = useState(false)
  const [editText, setEditText] = useState<Record<string, string>>({})

  const loadSide = useCallback(() => {
    if (!scopeBrand) return
    getJson<Record<string, unknown>>(`/api/captions/voice-bible?brand_id=${encodeURIComponent(scopeBrand)}`)
      .then(setVoiceBible)
      .catch(() => setVoiceBible(null))
    getJson<{ ok?: boolean; saved?: SavedCaption[] }>('/api/captions/saved')
      .then((r) => setSaved(r.saved || []))
      .catch(() => setSaved([]))
  }, [scopeBrand])

  useEffect(() => {
    loadSide()
  }, [loadSide])

  const baseBody = useCallback(
    () => ({
      brand_id: scopeBrand,
      user_brief: brief,
      n_survivors: 5,
    }),
    [scopeBrand, brief],
  )

  const handleGenerate = async () => {
    if (!scopeBrand) return
    setBusy(true)
    setError('')
    try {
      const res = await postJson<GenerateResponse>('/api/captions/v2/generate', baseBody())
      if (!res.ok) {
        setError(res.error || 'Generate failed')
        return
      }
      setSurvivors(res.survivors || [])
      setRejects(res.rejects_by_check || null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generate failed')
    } finally {
      setBusy(false)
    }
  }

  const cardAction = async (
    path: string,
    body: Record<string, unknown>,
    onOk: (res: GenerateResponse) => void,
  ) => {
    setBusy(true)
    try {
      const res = await postJson<GenerateResponse>(path, body)
      if (res.ok) onOk(res)
      else setError(res.error || 'Request failed')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/create" title="Captions">
        v2 caption studio — five survivors, per-card actions, voice bible on the side.{' '}
        <ClassicLink href="/?page=captions" label="Captions" />
      </PageIntro>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <HeroPanel icon={MessageSquareText} kicker="Studio" title="Brief → survivors">
          <textarea
            className={`${inputCls} mt-3 min-h-[100px]`}
            placeholder="What should this caption accomplish?"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
          />
          <Tip text="POST /api/captions/v2/generate with brand_id in body.">
            <button
              type="button"
              disabled={busy || !scopeBrand || !brief.trim()}
              onClick={handleGenerate}
              className="mt-3 rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
            >
              {busy ? 'Working…' : 'Generate 5'}
            </button>
          </Tip>
          {error ? <p className="mt-2 text-sm text-red">{error}</p> : null}

          <ul className="mt-6 space-y-3">
            {survivors.map((s, i) => (
              <li key={s.id || i} className="glass rounded-2xl border border-white/10 p-4">
                <Badge tone="green">Survivor {i + 1}</Badge>
                <p className="mt-2 text-sm whitespace-pre-wrap">{s.caption}</p>
                {s.route ? <p className="mt-1 text-xs text-tx3">Route: {s.route}</p> : null}
                <textarea
                  className={`${inputCls} mt-2 min-h-[60px]`}
                  placeholder="Edit before approve…"
                  value={editText[s.id || String(i)] ?? s.caption ?? ''}
                  onChange={(e) =>
                    setEditText((prev) => ({ ...prev, [s.id || String(i)]: e.target.value }))
                  }
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <Tip text="POST /api/captions/v2/more-like-this">
                    <button
                      type="button"
                      disabled={busy}
                      className="text-xs font-semibold text-ac hover:text-yel"
                      onClick={() =>
                        cardAction('/api/captions/v2/more-like-this', {
                          ...baseBody(),
                          liked_route: s.route,
                          liked_candidate_id: s.id,
                        }, (r) => setSurvivors(r.survivors || []))
                      }
                    >
                      More like this
                    </button>
                  </Tip>
                  <Tip text="POST /api/captions/v2/regenerate-different">
                    <button
                      type="button"
                      disabled={busy}
                      className="text-xs font-semibold text-ac hover:text-yel"
                      onClick={() =>
                        cardAction('/api/captions/v2/regenerate-different', {
                          ...baseBody(),
                          previous_route: s.route,
                        }, (r) => setSurvivors(r.survivors || []))
                      }
                    >
                      Regenerate different
                    </button>
                  </Tip>
                  <Tip text="POST /api/captions/v2/select">
                    <button
                      type="button"
                      disabled={busy}
                      className="text-xs font-semibold text-yel"
                      onClick={() =>
                        cardAction('/api/captions/v2/select', {
                          brand_id: scopeBrand,
                          candidate_id: s.id,
                          route: s.route,
                        }, () => loadSide())
                      }
                    >
                      Select
                    </button>
                  </Tip>
                  <Tip text="POST /api/captions/v2/edit-approve">
                    <button
                      type="button"
                      disabled={busy}
                      className="text-xs font-semibold text-yel"
                      onClick={() =>
                        cardAction('/api/captions/v2/edit-approve', {
                          brand_id: scopeBrand,
                          candidate_id: s.id,
                          caption: editText[s.id || String(i)] ?? s.caption,
                        }, () => loadSide())
                      }
                    >
                      Edit + approve
                    </button>
                  </Tip>
                </div>
              </li>
            ))}
          </ul>

          {rejects && Object.keys(rejects).length > 0 ? (
            <div className="mt-4">
              <button
                type="button"
                className="text-sm font-semibold text-tx2 hover:text-yel"
                onClick={() => setShowRejects((v) => !v)}
              >
                {showRejects ? 'Hide' : 'Show'} rejects by check
              </button>
              {showRejects ? (
                <pre className="mt-2 max-h-48 overflow-auto rounded-xl bg-bg2/80 p-3 text-xs text-tx3">
                  {JSON.stringify(rejects, null, 2)}
                </pre>
              ) : null}
            </div>
          ) : null}
        </HeroPanel>

        <aside className="space-y-4">
          <section className="glass rounded-2xl border border-white/10 p-4">
            <h2 className="text-sm font-semibold">Voice bible</h2>
            <pre className="mt-2 max-h-40 overflow-auto text-xs text-tx3">
              {voiceBible ? JSON.stringify(voiceBible, null, 2) : 'Loading…'}
            </pre>
          </section>
          <section className="glass rounded-2xl border border-white/10 p-4">
            <h2 className="text-sm font-semibold">Saved captions</h2>
            <ul className="mt-2 space-y-2 text-sm">
              {saved.length === 0 ? (
                <li className="text-tx3">None yet.</li>
              ) : (
                saved.map((row) => (
                  <li key={row.id} className="flex items-start justify-between gap-2">
                    <span className="line-clamp-2">{row.caption}</span>
                    <Tip text="DELETE /api/captions/saved/id">
                      <button
                        type="button"
                        className="shrink-0 text-xs text-red"
                        onClick={() =>
                          fetch(`/api/captions/saved/${encodeURIComponent(row.id || '')}`, {
                            method: 'DELETE',
                            credentials: 'same-origin',
                          }).then(loadSide)
                        }
                      >
                        Del
                      </button>
                    </Tip>
                  </li>
                ))
              )}
            </ul>
            <Tip text="POST /api/captions/save after you pick a winner.">
              <button
                type="button"
                className="mt-2 text-xs font-semibold text-ac"
                onClick={() =>
                  postJson('/api/captions/save', {
                    brand_id: scopeBrand,
                    caption: survivors[0]?.caption,
                  }).then(loadSide)
                }
              >
                Save first survivor
              </button>
            </Tip>
          </section>
        </aside>
      </div>
    </div>
  )
}
