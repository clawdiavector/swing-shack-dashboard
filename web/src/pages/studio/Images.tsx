import { ImageIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../../components/chrome'
import { ClassicLink, Tip } from '../../components/ui'
import { fetchVisualLibrary, fetchVisualLibraryStats, getJson, postJson } from '../../lib/api'

type ImageTab = 'generate' | 'lab' | 'library'

const TAB_OPTIONS = [
  { id: 'generate', label: 'Generate' },
  { id: 'lab', label: 'Lab' },
  { id: 'library', label: 'Library' },
]

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

export function Images() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as ImageTab) || 'generate'
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<unknown>(null)
  const [history, setHistory] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  useEffect(() => {
    if (!scopeBrand || tab !== 'generate') return
    getJson(`/api/image/outputs/${encodeURIComponent(scopeBrand)}`)
      .then(setHistory)
      .catch(() => setHistory(null))
  }, [scopeBrand, tab])

  const runGenerate = async () => {
    if (!scopeBrand) return
    setBusy(true)
    setError('')
    try {
      const spec = await getJson<Record<string, unknown>>(
        `/api/intel/generate_image?brand=${encodeURIComponent(scopeBrand)}`,
      )
      const rendered = await postJson('/api/image/generate', {
        brand_id: scopeBrand,
        prompt: prompt || (spec.prompt as string) || '',
      })
      setResult({ spec, rendered })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generate failed')
    } finally {
      setBusy(false)
    }
  }

  const runLab = async () => {
    setBusy(true)
    setError('')
    try {
      const overlay = await postJson('/api/image-lab/auto-overlay', {
        brand_id: scopeBrand,
        prompt,
      })
      setResult(overlay)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lab failed')
    } finally {
      setBusy(false)
    }
  }

  const runLibrary = async () => {
    if (!scopeBrand) return
    setBusy(true)
    try {
      const [images, stats, dna] = await Promise.all([
        fetchVisualLibrary(scopeBrand),
        fetchVisualLibraryStats(scopeBrand),
        getJson(`/api/visual-dna/${encodeURIComponent(scopeBrand)}/search?q=${encodeURIComponent(prompt)}`),
      ])
      setResult({ images, stats, dna })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Library failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/create" title="Images">
        Generate, lab overlay, and visual library — standalone HTML stays reachable.{' '}
        <ClassicLink href="/?page=imagegen" label="Image gen" /> ·{' '}
        <ClassicLink href="/image-lab" label="Image lab" /> ·{' '}
        <ClassicLink href="/visualizer" label="Visual library" />
      </PageIntro>

      <FilterChips value={tab} options={TAB_OPTIONS} onChange={setTab} />

      <HeroPanel icon={ImageIcon} kicker="Studio" title={TAB_OPTIONS.find((t) => t.id === tab)?.label || tab}>
        <textarea
          className={`${inputCls} mt-2 min-h-[80px]`}
          placeholder="Prompt or search…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {tab === 'generate' ? (
            <Tip text="GET generate_image spec then POST /api/image/generate">
              <button
                type="button"
                disabled={busy}
                onClick={runGenerate}
                className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
              >
                Generate
              </button>
            </Tip>
          ) : null}
          {tab === 'lab' ? (
            <>
              <Tip text="POST /api/image-lab/auto-overlay">
                <button
                  type="button"
                  disabled={busy}
                  onClick={runLab}
                  className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
                >
                  Auto overlay
                </button>
              </Tip>
              <Tip text="POST /api/image-lab/save-as-asset">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    postJson('/api/image-lab/save-as-asset', { brand_id: scopeBrand }).then(setResult)
                  }
                  className="rounded-full border border-white/15 px-4 py-2 text-sm font-semibold"
                >
                  Save as asset
                </button>
              </Tip>
            </>
          ) : null}
          {tab === 'library' ? (
            <Tip text="Visual library + DNA search">
              <button
                type="button"
                disabled={busy}
                onClick={runLibrary}
                className="rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
              >
                Load library
              </button>
            </Tip>
          ) : null}
        </div>
        {error ? <p className="mt-2 text-sm text-red">{error}</p> : null}
        {tab === 'generate' && history ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-semibold">Output history</summary>
            <pre className="mt-2 max-h-40 overflow-auto text-xs">{JSON.stringify(history, null, 2)}</pre>
          </details>
        ) : null}
        <pre className="mt-4 max-h-[420px] overflow-auto rounded-2xl bg-bg2/80 p-4 text-xs">
          {result ? JSON.stringify(result, null, 2) : 'Run an action above.'}
        </pre>
      </HeroPanel>
    </div>
  )
}
