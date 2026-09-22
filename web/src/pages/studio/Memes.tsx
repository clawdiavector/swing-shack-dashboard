import { Laugh } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../../components/chrome'
import { ClassicLink, Tip } from '../../components/ui'
import { fetchMemeCatalog, getJson, postJson } from '../../lib/api'

type MemeTab = 'lord' | 'lab'

const TAB_OPTIONS = [
  { id: 'lord', label: 'Meme Lord' },
  { id: 'lab', label: 'Meme lab' },
]

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

export function Memes() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as MemeTab) || 'lord'
  const [brief, setBrief] = useState('')
  const [result, setResult] = useState<unknown>(null)
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

  const runLord = async () => {
    if (!scopeBrand) return
    setBusy(true)
    setError('')
    try {
      const catalog = await fetchMemeCatalog(scopeBrand)
      const generated = await postJson(`/api/intel/generate_meme?brand=${encodeURIComponent(scopeBrand)}`, {
        brief,
      })
      setResult({ catalog, generated })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Meme Lord failed')
    } finally {
      setBusy(false)
    }
  }

  const runLab = async () => {
    setBusy(true)
    setError('')
    try {
      const templates = await getJson('/api/meme/templates')
      const applied = await postJson(`/api/intel/meme_apply?brand=${encodeURIComponent(scopeBrand)}`, {
        template_id: brief,
      })
      setResult({ templates, applied })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Meme lab failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/create" title="Memes">
        Meme Lord and template lab — classic desks stay on disk.{' '}
        <ClassicLink href="/?page=memes" label="Meme Lord" /> ·{' '}
        <ClassicLink href="/meme-lab" label="Meme lab" />
      </PageIntro>

      <FilterChips value={tab} options={TAB_OPTIONS} onChange={setTab} />

      <HeroPanel icon={Laugh} kicker="Studio" title={tab === 'lord' ? 'Meme Lord' : 'Meme lab'}>
        <input
          className={`${inputCls} mt-2`}
          placeholder={tab === 'lab' ? 'Template id…' : 'Brief for meme…'}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
        />
        <Tip text={tab === 'lord' ? 'generate_meme + catalog' : 'templates + meme_apply'}>
          <button
            type="button"
            disabled={busy || !scopeBrand}
            onClick={tab === 'lord' ? runLord : runLab}
            className="mt-3 rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
          >
            {busy ? 'Working…' : tab === 'lord' ? 'Generate meme' : 'Apply template'}
          </button>
        </Tip>
        {error ? <p className="mt-2 text-sm text-red">{error}</p> : null}
        <pre className="mt-4 max-h-[420px] overflow-auto rounded-2xl bg-bg2/80 p-4 text-xs">
          {result ? JSON.stringify(result, null, 2) : 'Run an action above.'}
        </pre>
      </HeroPanel>
    </div>
  )
}
