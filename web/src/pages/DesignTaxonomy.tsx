import { Check, Palette, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Badge } from '../components/ui'
import {
  approveDesignTaxonomyItem,
  fetchDesignTaxonomy,
  type TaxonomyMethod,
  type TaxonomyPayload,
  type TaxonomyPost,
  type TaxonomyStyle,
  type TaxonomyTemplateRow,
  type TaxonomyType,
  unapproveDesignTaxonomyItem,
} from '../lib/api'
import { DetailDrawer, TemplateCard } from './results/Templates'

const SECTIONS = [
  { key: 'styles', label: 'Styles' },
  { key: 'templates', label: 'Templates' },
  { key: 'types', label: 'Types' },
  { key: 'posts', label: 'Posts' },
  { key: 'methods', label: 'Methods' },
] as const

type SectionKey = (typeof SECTIONS)[number]['key']

function StackToggle({
  stack,
  onChange,
}: {
  stack: 'not_approved' | 'approved'
  onChange: (s: 'not_approved' | 'approved') => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={() => onChange('not_approved')}
        className={`rounded-xl px-4 py-2 text-sm font-semibold ${
          stack === 'not_approved'
            ? 'bg-ac text-bg'
            : 'border border-white/15 text-tx2 hover:bg-white/5'
        }`}
      >
        Not approved yet
      </button>
      <button
        type="button"
        onClick={() => onChange('approved')}
        className={`rounded-xl px-4 py-2 text-sm font-semibold ${
          stack === 'approved'
            ? 'bg-green text-bg'
            : 'border border-white/15 text-tx2 hover:bg-white/5'
        }`}
      >
        Approved
      </button>
    </div>
  )
}

function ItemRow({
  title,
  subtitle,
  onClick,
}: {
  title: string
  subtitle?: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass flex w-full flex-col gap-1 rounded-xl border border-white/10 px-4 py-3 text-left transition hover:border-ac/40"
    >
      <span className="font-semibold text-tx">{title}</span>
      {subtitle ? <span className="text-sm text-tx3">{subtitle}</span> : null}
    </button>
  )
}

function ApprovalActions({
  section,
  id,
  approval,
  onDone,
}: {
  section: SectionKey
  id: string
  approval: { status: string }
  onDone: () => void
}) {
  const [busy, setBusy] = useState(false)
  const approved = approval.status === 'approved'

  const toggle = async () => {
    setBusy(true)
    try {
      if (approved) {
        await unapproveDesignTaxonomyItem(section, id)
      } else {
        await approveDesignTaxonomyItem(section, id)
      }
      onDone()
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      disabled={busy}
      onClick={toggle}
      className={`inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold ${
        approved
          ? 'border border-white/15 text-tx2 hover:bg-white/5'
          : 'bg-yel text-bg hover:bg-yel/90'
      }`}
    >
      <Check className="h-4 w-4" />
      {approved ? 'Unapprove' : 'Approve'}
    </button>
  )
}

function StyleDrawer({
  style,
  onClose,
  onRefresh,
}: {
  style: TaxonomyStyle
  onClose: () => void
  onRefresh: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal
    >
      <div className="glass max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/15 p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-semibold">{style.name}</h2>
            <p className="mt-1 text-sm text-tx2">{style.summary}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-2 hover:bg-white/10" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="mb-4">
          <ApprovalActions section="styles" id={style.id} approval={style.approval} onDone={onRefresh} />
        </div>
        {style.references?.length ? (
          <section className="mb-4">
            <h3 className="text-sm font-semibold text-tx">References</h3>
            <ul className="mt-2 space-y-2 text-sm text-tx2">
              {style.references.map((ref) => (
                <li key={ref.label}>
                  <span className="font-medium text-tx">{ref.label}</span>
                  {ref.path ? <span className="ml-2 font-mono text-xs text-tx3">{ref.path}</span> : null}
                  {ref.note ? <p className="text-tx3">{ref.note}</p> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {style.roles?.colour_roles ? (
          <section className="mb-4">
            <h3 className="text-sm font-semibold text-tx">Colour roles</h3>
            <ul className="mt-2 space-y-1 text-sm text-tx2">
              {Object.entries(style.roles.colour_roles).map(([key, row]) => (
                <li key={key}>
                  {key}: <Badge tone="mute">{row.from}</Badge> {row.role}
                  {row.hex ? <span className="ml-2 font-mono text-xs">{row.hex}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {style.roles?.font_roles ? (
          <section className="mb-4">
            <h3 className="text-sm font-semibold text-tx">Font roles</h3>
            <ul className="mt-2 space-y-1 text-sm text-tx2">
              {Object.entries(style.roles.font_roles).map(([key, row]) => (
                <li key={key}>
                  {key}: <Badge tone="mute">{row.from}</Badge> {row.family || row.role}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {style.roles?.fixed ? (
          <section className="mb-4">
            <h3 className="text-sm font-semibold text-tx">Fixed parts</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-tx2">
              {Object.entries(style.roles.fixed).map(([k, v]) => (
                <li key={k}>
                  <span className="font-medium capitalize">{k.replace(/_/g, ' ')}</span>: {v}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {style.method_id ? (
          <p className="mb-4 text-sm text-tx2">
            Method: <span className="font-mono text-tx">{style.method_id}</span>
          </p>
        ) : null}
        {style.examples?.length ? (
          <section className="mb-4">
            <h3 className="text-sm font-semibold text-tx">Examples</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-tx2">
              {style.examples.map((ex) => (
                <li key={ex}>{ex}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {style.checks?.length ? (
          <section>
            <h3 className="text-sm font-semibold text-tx">Checks</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-tx2">
              {style.checks.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  )
}

function GenericDrawer({
  title,
  section,
  id,
  approval,
  onClose,
  onRefresh,
  children,
}: {
  title: string
  section: SectionKey
  id: string
  approval: { status: string }
  onClose: () => void
  onRefresh: () => void
  children: ReactNode
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      role="dialog"
      aria-modal
    >
      <div className="glass max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/15 p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-2 hover:bg-white/10" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="mb-4">
          <ApprovalActions section={section} id={id} approval={approval} onDone={onRefresh} />
        </div>
        {children}
      </div>
    </div>
  )
}

export function DesignTaxonomy() {
  const { brandId: rawBrandId, brandLabel } = useBrand()
  const brandId = rawBrandId || 'swing-shack'
  const [searchParams, setSearchParams] = useSearchParams()
  const section = (searchParams.get('section') as SectionKey) || 'styles'
  const [stack, setStack] = useState<'not_approved' | 'approved'>('not_approved')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<TaxonomyPayload | null>(null)
  const [selectedStyle, setSelectedStyle] = useState<TaxonomyStyle | null>(null)
  const [selectedType, setSelectedType] = useState<TaxonomyType | null>(null)
  const [selectedMethod, setSelectedMethod] = useState<TaxonomyMethod | null>(null)
  const [selectedPost, setSelectedPost] = useState<TaxonomyPost | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<TaxonomyTemplateRow | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    fetchDesignTaxonomy(brandId)
      .then((payload) => {
        if (payload.error && !payload.styles?.length) {
          setError(payload.error)
        }
        setData(payload)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [brandId])

  useEffect(() => {
    load()
  }, [load])

  const setSection = (key: SectionKey) => {
    const next = new URLSearchParams(searchParams)
    next.set('section', key)
    setSearchParams(next, { replace: true })
  }

  const filterStack = <T extends { approval: { status: string } }>(rows: T[]) =>
    rows.filter((r) =>
      stack === 'approved' ? r.approval.status === 'approved' : r.approval.status !== 'approved',
    )

  const styles = useMemo(() => filterStack(data?.styles || []), [data?.styles, stack])
  const types = useMemo(() => filterStack(data?.types || []), [data?.types, stack])
  const methods = useMemo(() => filterStack(data?.methods || []), [data?.methods, stack])
  const posts = useMemo(() => filterStack(data?.posts || []), [data?.posts, stack])
  const templates = useMemo(() => filterStack(data?.templates || []), [data?.templates, stack])

  return (
    <div className="space-y-6">
      <PageIntro icon={Palette} badge="Design taxonomy" here="/design" title="Taxonomy of Design">
        Named styles, templates, types, posts and methods for {brandLabel || brandId}. Approve what
        agents may pull.
      </PageIntro>

      <div className="flex flex-wrap gap-2">
        {SECTIONS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setSection(tab.key)}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${
              section === tab.key
                ? 'bg-ac text-bg'
                : 'border border-white/15 text-tx2 hover:bg-white/5'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <StackToggle stack={stack} onChange={setStack} />

      {loading ? <div className="h-40 animate-pulse rounded-2xl bg-bg3" /> : null}
      {error ? (
        <p className="rounded-2xl border border-red/30 bg-red/5 px-4 py-3 text-sm text-red">{error}</p>
      ) : null}

      {!loading && section === 'styles' ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {styles.map((s) => (
            <ItemRow key={s.id} title={s.name} subtitle={s.summary} onClick={() => setSelectedStyle(s)} />
          ))}
          {!styles.length ? <p className="text-sm text-tx3">Nothing in this stack.</p> : null}
        </div>
      ) : null}

      {!loading && section === 'types' ? (
        <div className="grid gap-2">
          {types.map((t) => (
            <ItemRow
              key={t.id}
              title={t.name}
              subtitle={t.meaning}
              onClick={() => setSelectedType(t)}
            />
          ))}
        </div>
      ) : null}

      {!loading && section === 'methods' ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {methods.map((m) => (
            <ItemRow key={m.id} title={m.name} subtitle={m.cost_notes} onClick={() => setSelectedMethod(m)} />
          ))}
        </div>
      ) : null}

      {!loading && section === 'posts' ? (
        <div className="grid gap-2">
          {posts.map((p) => (
            <ItemRow
              key={p.id}
              title={p.title || p.id}
              subtitle={`${p.style} · ${p.campaign || '—'} · ${p.date || '—'} · ${p.status}`}
              onClick={() => setSelectedPost(p)}
            />
          ))}
        </div>
      ) : null}

      {!loading && section === 'templates' ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {templates.map((t) => (
            <TemplateCard key={t.template_id} template={t} onSelect={() => setSelectedTemplate(t)} />
          ))}
          {!templates.length ? <p className="text-sm text-tx3">Nothing in this stack.</p> : null}
        </div>
      ) : null}

      {selectedStyle ? (
        <StyleDrawer style={selectedStyle} onClose={() => setSelectedStyle(null)} onRefresh={load} />
      ) : null}

      {selectedType ? (
        <GenericDrawer
          title={selectedType.name}
          section="types"
          id={selectedType.id}
          approval={selectedType.approval}
          onClose={() => setSelectedType(null)}
          onRefresh={load}
        >
          <p className="text-sm text-tx2">{selectedType.meaning}</p>
          <p className="mt-2 text-sm text-tx3">
            Needs photo: {selectedType.needs_photo ? 'Yes' : 'No'}
          </p>
          <div className="mt-4 space-y-2 text-sm text-tx2">
            {Object.entries(selectedType.templates || {}).map(([brand, ids]) => (
              <div key={brand}>
                <span className="font-semibold text-ac">{brand}</span>:{' '}
                {ids.length ? ids.join(', ') : '—'}
              </div>
            ))}
          </div>
        </GenericDrawer>
      ) : null}

      {selectedMethod ? (
        <GenericDrawer
          title={selectedMethod.name}
          section="methods"
          id={selectedMethod.id}
          approval={selectedMethod.approval}
          onClose={() => setSelectedMethod(null)}
          onRefresh={load}
        >
          <p className="text-sm text-tx2">{selectedMethod.cost_notes}</p>
          <p className="mt-2 font-mono text-xs text-tx3">{selectedMethod.kind}</p>
          {selectedMethod.tools?.length ? (
            <p className="mt-2 text-sm text-tx2">Tools: {selectedMethod.tools.join(', ')}</p>
          ) : null}
        </GenericDrawer>
      ) : null}

      {selectedPost ? (
        <GenericDrawer
          title={selectedPost.title || selectedPost.id}
          section="posts"
          id={selectedPost.id}
          approval={selectedPost.approval}
          onClose={() => setSelectedPost(null)}
          onRefresh={load}
        >
          <dl className="space-y-2 text-sm text-tx2">
            <div>
              <dt className="text-tx3">Style</dt>
              <dd>{selectedPost.style}</dd>
            </div>
            <div>
              <dt className="text-tx3">Status</dt>
              <dd>{selectedPost.status}</dd>
            </div>
            <div>
              <dt className="text-tx3">Where it lives</dt>
              <dd>
                {selectedPost.campaign || '—'} · {selectedPost.date || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-tx3">Type</dt>
              <dd className="text-tx3">—</dd>
            </div>
          </dl>
        </GenericDrawer>
      ) : null}

      {selectedTemplate ? (
        <>
          <DetailDrawer template={selectedTemplate} onClose={() => setSelectedTemplate(null)} />
          <div className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2">
            <ApprovalActions
              section="templates"
              id={selectedTemplate.template_id}
              approval={selectedTemplate.approval}
              onDone={load}
            />
          </div>
        </>
      ) : null}
    </div>
  )
}
