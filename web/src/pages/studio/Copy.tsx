import { PenLine } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../../components/chrome'
import { ClassicLink, Tip } from '../../components/ui'
import { fetchMemeCatalog, fetchVisualLibrary, getJson, postJson } from '../../lib/api'

type CopyTab = 'headlines' | 'hooks' | 'ctas' | 'hashtags' | 'library'

const TAB_OPTIONS = [
  { id: 'headlines', label: 'Headlines' },
  { id: 'hooks', label: 'Hooks' },
  { id: 'ctas', label: 'CTAs' },
  { id: 'hashtags', label: 'Hashtags' },
  { id: 'library', label: 'Library' },
]

const CLASSIC: Record<CopyTab, string> = {
  headlines: '/?page=headlines',
  hooks: '/?page=hooks',
  ctas: '/?page=ctas',
  hashtags: '/?page=hashtagseo',
  library: '/?page=library',
}

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx focus:border-ac focus:outline-none'

export function Copy() {
  const { brandId } = useBrand()
  const scopeBrand = brandId ?? ''
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as CopyTab) || 'headlines'
  const [payload, setPayload] = useState<unknown>(null)
  const [error, setError] = useState('')
  const [topic, setTopic] = useState('')
  const [loading, setLoading] = useState(false)

  const setTab = useCallback(
    (id: string) => {
      const p = new URLSearchParams(params)
      p.set('tab', id)
      setParams(p, { replace: true })
    },
    [params, setParams],
  )

  const loadTab = useCallback(async () => {
    if (!scopeBrand) return
    setLoading(true)
    setError('')
    try {
      let data: unknown
      const b = encodeURIComponent(scopeBrand)
      switch (tab) {
        case 'headlines':
          data = await postJson(`/api/intel/generate_headlines?brand=${b}`, { topic, count: 8 })
          break
        case 'hooks':
          data = await getJson(`/api/intel/hooks?brand=${b}`)
          break
        case 'ctas':
          data = await getJson(`/api/intel/cta_knowledge?brand=${b}`)
          break
        case 'hashtags':
          data = await getJson(`/api/intel/hashtags?brand=${b}`)
          break
        case 'library': {
          const [search, assets, visual, memes, inbox] = await Promise.all([
            getJson(`/api/search?brand=${b}&q=${encodeURIComponent(topic || '')}`),
            getJson(`/api/assets?brand=${b}&limit=20`),
            fetchVisualLibrary(scopeBrand),
            fetchMemeCatalog(scopeBrand),
            getJson(`/api/intel/review_inbox?brand=${b}`),
          ])
          data = { search, assets, visual, memes, inbox }
          break
        }
        default:
          data = null
      }
      setPayload(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Load failed')
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [scopeBrand, tab, topic])

  useEffect(() => {
    loadTab()
  }, [loadTab])

  const tabLabel = useMemo(() => TAB_OPTIONS.find((t) => t.id === tab)?.label || tab, [tab])

  return (
    <div className="space-y-6">
      <PageIntro here="/create" title="Copy cluster">
        Headlines, hooks, CTAs, hashtags, and cross-domain library — intel reads use ?brand=.{' '}
        <ClassicLink href={CLASSIC[tab]} label={tabLabel} />
      </PageIntro>

      <FilterChips value={tab} options={TAB_OPTIONS} onChange={setTab} />

      <HeroPanel icon={PenLine} kicker="Studio" title={tabLabel}>
        {tab === 'headlines' || tab === 'library' ? (
          <input
            className={`${inputCls} mt-2 max-w-md`}
            placeholder={tab === 'library' ? 'Search library…' : 'Topic for headlines…'}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        ) : null}
        <Tip text={`Refresh ${tab} from Classic-matching endpoints.`}>
          <button
            type="button"
            disabled={loading || !scopeBrand}
            onClick={loadTab}
            className="mt-3 rounded-full border border-white/15 px-4 py-2 text-sm font-semibold hover:border-ac disabled:opacity-50"
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </Tip>
        {error ? <p className="mt-2 text-sm text-red">{error}</p> : null}
        <pre className="mt-4 max-h-[480px] overflow-auto rounded-2xl bg-bg2/80 p-4 text-xs text-tx2">
          {payload ? JSON.stringify(payload, null, 2) : loading ? '…' : 'No data'}
        </pre>
      </HeroPanel>
    </div>
  )
}
