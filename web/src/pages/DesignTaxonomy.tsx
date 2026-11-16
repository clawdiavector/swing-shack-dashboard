import { Check, Film, Palette, Search, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PageIntro } from '../components/chrome'
import { Badge } from '../components/ui'
import {
  approveDesignTaxonomyItem,
  designMediaUrl,
  fetchDesignTaxonomy,
  resolveAssetUrl,
  type TaxonomyMethod,
  type TaxonomyPayload,
  type TaxonomyPicture,
  type TaxonomyPost,
  type TaxonomyStyle,
  type TaxonomyTemplateRow,
  type TaxonomyType,
  unapproveDesignTaxonomyItem,
} from '../lib/api'

const SECTIONS = [
  { key: 'styles', label: 'Styles' },
  { key: 'templates', label: 'Templates' },
  { key: 'types', label: 'Types' },
  { key: 'posts', label: 'Posts' },
  { key: 'methods', label: 'Methods' },
] as const

type SectionKey = (typeof SECTIONS)[number]['key']
type Stack = 'not_approved' | 'approved'

const BRANDS = [
  { id: 'all', label: 'All brands' },
  { id: 'swing-shack', label: 'Swing Shack' },
  { id: 'stick', label: 'Stick' },
  { id: 'bag-drop', label: 'Bag Drop' },
]
const brandLabel = (id: string) => BRANDS.find((b) => b.id === id)?.label || id

/** One picture per post for tiles: the first still, else the reel's poster frame. */
const lead = (p: TaxonomyPost): TaxonomyPicture | undefined => p.pictures?.[0]
const pictured = (p: TaxonomyPost) => !!lead(p)

/** A finished post, as opposed to a photo, supplier picture, work file or sheet that goes into one. */
const finishedPic = (x: TaxonomyPicture) => !x.kind || x.kind === 'post'
const finishedPost = (p: TaxonomyPost) => !p.kind || p.kind === 'post'
const KIND_LABEL: Record<string, string> = {
  post: 'Finished post',
  photo: 'Our photo',
  product: 'Supplier picture',
  part: 'Work file',
  sheet: 'Sheet',
}
const ROLE_RANK: Record<string, number> = { feed: 0, image: 1, gbp: 2, story: 3, reel: 4 }

type Nav = (section: SectionKey, id: string) => void

// ---------------------------------------------------------------- pieces

function Pic({
  pic,
  size = 'thumb',
  alt = '',
  className = '',
}: {
  pic?: TaxonomyPicture
  size?: 'thumb' | 'mid'
  alt?: string
  className?: string
}) {
  const name = pic ? (size === 'mid' ? pic.mid || pic.thumb : pic.thumb) : ''
  if (!name) {
    return <div className={`grid place-items-center bg-bg2 text-xs text-tx3 ${className}`}>No picture</div>
  }
  return <img src={designMediaUrl(name)} alt={alt} loading="lazy" className={`bg-bg2 object-cover ${className}`} />
}

type Shot = { post: TaxonomyPost; pic: TaxonomyPicture }

function Mosaic({ shots, empty }: { shots: Shot[]; empty: string }) {
  const shown = shots.slice(0, 5)
  if (!shown.length) {
    return (
      <div className="grid aspect-[16/9] place-items-center rounded-xl border border-dashed border-white/15 px-4 text-center text-xs text-tx3">
        {empty}
      </div>
    )
  }
  if (shown.length < 5) {
    return (
      <div className={`grid aspect-[16/9] gap-1 overflow-hidden rounded-xl ${shown.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
        {shown.slice(0, 2).map((s) => (
          <Pic key={s.pic.thumb} pic={s.pic} size="mid" className="h-full w-full" />
        ))}
      </div>
    )
  }
  return (
    <div className="grid aspect-[16/9] grid-cols-4 grid-rows-2 gap-1 overflow-hidden rounded-xl">
      <Pic pic={shown[0].pic} size="mid" className="col-span-2 row-span-2 h-full w-full" />
      {shown.slice(1).map((s) => (
        <Pic key={s.pic.thumb} pic={s.pic} className="h-full w-full" />
      ))}
    </div>
  )
}

/** A short row of small pictures that open their post. */
function Thumbs({ shots, onOpen, limit = 8 }: { shots: Shot[]; onOpen: (p: TaxonomyPost) => void; limit?: number }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {shots.slice(0, limit).map((sh) => (
        <button
          key={sh.pic.thumb}
          type="button"
          onClick={() => onOpen(sh.post)}
          title={sh.post.title}
          className="overflow-hidden rounded-lg border border-white/10 hover:border-ac/60"
        >
          <Pic pic={sh.pic} className="h-24 w-[4.75rem]" />
        </button>
      ))}
      {shots.length > limit ? <span className="self-center px-1 text-xs text-tx3">+{shots.length - limit}</span> : null}
    </div>
  )
}

function Chip({
  label,
  hint,
  thumb,
  onClick,
}: {
  label: string
  hint?: string
  thumb?: ReactNode
  onClick?: () => void
}) {
  const body = (
    <>
      {thumb ? <span className="h-8 w-8 shrink-0 overflow-hidden rounded-md">{thumb}</span> : null}
      <span className="flex flex-col text-left leading-tight">
        <span className="text-sm font-semibold text-tx">{label}</span>
        {hint ? <span className="text-xs text-tx3">{hint}</span> : null}
      </span>
    </>
  )
  const cls = 'inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-2 py-1.5'
  if (!onClick) return <span className={cls}>{body}</span>
  return (
    <button type="button" onClick={onClick} className={`${cls} transition hover:border-ac/50`}>
      {body}
    </button>
  )
}

function Missing({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-xl border border-dashed border-white/15 px-3 py-2 text-xs text-tx3">
      {children}
    </span>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-tx3">{label}</p>
      <div className="flex flex-wrap gap-2 text-sm text-tx2">{children}</div>
    </div>
  )
}

function ApprovalButton({
  section,
  id,
  approval,
  onDone,
}: {
  section: SectionKey
  id: string
  approval: { status: string; by?: string | null }
  onDone: () => void
}) {
  const [busy, setBusy] = useState(false)
  const approved = approval.status === 'approved'
  const toggle = async () => {
    setBusy(true)
    try {
      if (approved) await unapproveDesignTaxonomyItem(section, id)
      else await approveDesignTaxonomyItem(section, id)
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
        approved ? 'border border-white/15 text-tx2 hover:bg-white/5' : 'bg-yel text-bg hover:bg-yel/90'
      }`}
    >
      <Check className="h-4 w-4" />
      {approved ? `Approved${approval.by ? ` by ${approval.by}` : ''} · Unapprove` : 'Approve'}
    </button>
  )
}

function Panel({
  title,
  kicker,
  actions,
  onClose,
  children,
}: {
  title: string
  kicker?: string
  actions?: ReactNode
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-3 sm:p-6"
      role="dialog"
      aria-modal
      onClick={onClose}
    >
      <div
        className="glass my-auto w-full max-w-5xl rounded-2xl border border-white/15 p-4 shadow-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {kicker ? <p className="text-xs font-semibold uppercase tracking-wide text-ac">{kicker}</p> : null}
            <h2 className="font-display text-2xl font-semibold">{title}</h2>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {actions}
            <button type="button" onClick={onClose} className="rounded-lg p-2 hover:bg-white/10" aria-label="Close">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-black/90 p-4" onClick={onClose}>
      <img src={src} alt="" className="max-h-full max-w-full rounded-lg object-contain" />
    </div>
  )
}

type Format = 'all' | 'static' | 'story' | 'reel'

const isStory = (x: TaxonomyPicture) => x.role === 'story'
const FORMAT_PIC: Record<Format, (x: TaxonomyPicture) => boolean> = {
  all: () => true,
  static: (x) => !x.video && !isStory(x),
  story: isStory,
  reel: (x) => x.video,
}
/** The picture a tile leads with: the first one of the chosen format, else the post's first. */
const leadFor = (p: TaxonomyPost, f: Format) => (p.pictures || []).find(FORMAT_PIC[f]) || lead(p)

function PostTile({
  post,
  onOpen,
  format = 'all',
  labelOf,
}: {
  post: TaxonomyPost
  onOpen: () => void
  format?: Format
  labelOf?: (post: TaxonomyPost, pic: TaxonomyPicture) => string
}) {
  const pic = leadFor(post, format)
  const kinds = [
    post.pictures?.some(FORMAT_PIC.story) ? 'story' : '',
    post.pictures?.some(FORMAT_PIC.reel) ? 'reel' : '',
  ].filter(Boolean)
  return (
    <button
      type="button"
      onClick={onOpen}
      title={post.title}
      className="group relative aspect-[4/5] overflow-hidden rounded-xl border border-white/10 bg-bg2 text-left transition hover:border-ac/60"
    >
      {pic ? (
        <Pic pic={pic} className="h-full w-full transition group-hover:scale-[1.03]" />
      ) : (
        <div className="flex h-full w-full flex-col justify-between bg-white/[0.03] p-2 text-[11px] leading-snug text-tx2">
          <span className="line-clamp-6">{post.title}</span>
          <span className="text-tx3">{post.date || 'no picture'}</span>
        </div>
      )}
      {pic?.video ? (
        <span className="absolute right-1.5 top-1.5 rounded-md bg-black/70 p-1">
          <Film className="h-3 w-3 text-white" />
        </span>
      ) : null}
      {pic ? (
        <span className="absolute inset-x-0 bottom-0 flex flex-wrap gap-1 bg-gradient-to-t from-black/80 to-transparent p-1.5 pt-6 text-[10px] font-semibold text-white">
          {kinds.map((k) => (
            <span key={k} className="rounded bg-ac px-1 uppercase text-bg">
              {k}
            </span>
          ))}
          <span className="line-clamp-1 rounded bg-black/50 px-1">
            {labelOf?.(post, pic) || (pic.styles?.length ? pic.styles.join(' · ') : post.campaign || post.brand)}
          </span>
        </span>
      ) : null}
      {post.approval.status === 'approved' ? (
        <span className="absolute left-1.5 top-1.5 rounded-full bg-yel p-0.5">
          <Check className="h-3 w-3 text-bg" />
        </span>
      ) : null}
    </button>
  )
}

function ShotGrid({ shots, onOpen, limit = 24 }: { shots: Shot[]; onOpen: (p: TaxonomyPost) => void; limit?: number }) {
  const [more, setMore] = useState(false)
  const rows = more ? shots : shots.slice(0, limit)
  return (
    <>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {rows.map((sh) => (
          <button
            key={sh.pic.thumb}
            type="button"
            onClick={() => onOpen(sh.post)}
            title={sh.post.title}
            className="relative aspect-[4/5] overflow-hidden rounded-xl border border-white/10 bg-bg2 hover:border-ac/60"
          >
            <Pic pic={sh.pic} className="h-full w-full" />
            {sh.pic.video ? (
              <span className="absolute right-1.5 top-1.5 rounded-md bg-black/70 p-1">
                <Film className="h-3 w-3 text-white" />
              </span>
            ) : null}
          </button>
        ))}
      </div>
      {!more && shots.length > limit ? (
        <button type="button" onClick={() => setMore(true)} className="mt-3 text-sm font-semibold text-ac">
          Show all {shots.length}
        </button>
      ) : null}
    </>
  )
}

function PostGrid({ posts, onOpen, limit = 24 }: { posts: TaxonomyPost[]; onOpen: (p: TaxonomyPost) => void; limit?: number }) {
  const [more, setMore] = useState(false)
  const rows = more ? posts : posts.slice(0, limit)
  return (
    <>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {rows.map((p) => (
          <PostTile key={p.id} post={p} onOpen={() => onOpen(p)} />
        ))}
      </div>
      {!more && posts.length > limit ? (
        <button type="button" onClick={() => setMore(true)} className="mt-3 text-sm font-semibold text-ac">
          Show all {posts.length}
        </button>
      ) : null}
    </>
  )
}

// ---------------------------------------------------------------- details

type Ctx = {
  data: TaxonomyPayload
  go: Nav
  reload: () => void
  styleById: Map<string, TaxonomyStyle>
  methodById: Map<string, TaxonomyMethod>
  templateById: Map<string, TaxonomyTemplateRow>
  postsByStyle: Map<string, TaxonomyPost[]>
  /** Best pictures per style: the seed's named examples, then finished posts, then raw photos. */
  shotsByStyle: Map<string, Shot[]>
  typesByTemplate: Map<string, TaxonomyType[]>
  typeById: Map<string, TaxonomyType>
  postById: Map<string, TaxonomyPost>
  /** Photos and work files that carry a style (what the look is made from). */
  materialByStyle: Map<string, Shot[]>
  shotsByType: Map<string, Shot[]>
  shotsByTemplate: Map<string, Shot[]>
  /** Finished posts made from a picture, keyed by that picture's thumb. */
  usedIn: Map<string, Shot[]>
}

const tplPic = (t?: TaxonomyTemplateRow) => resolveAssetUrl(t?.preview_urls?.[0])

function StyleDetail({
  style,
  ctx,
  onClose,
  openPost,
}: {
  style: TaxonomyStyle
  ctx: Ctx
  onClose: () => void
  openPost: (p: TaxonomyPost) => void
}) {
  const shots = ctx.shotsByStyle.get(style.id) || []
  const material = ctx.materialByStyle.get(style.id) || []
  const method = style.method_id ? ctx.methodById.get(style.method_id) : undefined
  const [more, setMore] = useState(false)
  const fixed = Object.entries(style.roles?.fixed || {})
  const colours = Object.entries(style.roles?.colour_roles || {})
  const fonts = Object.entries(style.roles?.font_roles || {})
  const brands = Array.from(new Set(shots.map((sh) => sh.post.brand).filter(Boolean)))
  const typeCounts = new Map<string, number>()
  for (const sh of shots) if (sh.pic.type) typeCounts.set(sh.pic.type, (typeCounts.get(sh.pic.type) || 0) + 1)
  const hasDetails = fixed.length > 1 || colours.length || fonts.length || style.checks?.length || style.references?.length
  return (
    <Panel
      title={style.name}
      kicker={style.candidate ? 'Style · new name from the picture breakdown' : 'Style'}
      onClose={onClose}
      actions={<ApprovalButton section="styles" id={style.id} approval={style.approval} onDone={ctx.reload} />}
    >
      <p className="mb-3 text-sm text-tx2">{style.summary}</p>
      <div className="mb-5 flex flex-wrap gap-2">
        {method ? <Chip label={method.name} hint="made with" onClick={() => ctx.go('methods', method.id)} /> : null}
        {brands.map((b) => (
          <Chip key={b} label={brandLabel(b)} hint="brand" />
        ))}
        {[...typeCounts.entries()]
          .sort((a, b) => b[1] - a[1])
          .map(([id, n]) => (
            <Chip key={id} label={ctx.typeById.get(id)?.name || id} hint={`${n} pictures`} onClick={() => ctx.go('types', id)} />
          ))}
      </div>

      <h3 className="mb-2 text-sm font-semibold text-tx">
        Posts in this look <span className="font-normal text-tx3">· {shots.length} pictures</span>
      </h3>
      {shots.length ? (
        <ShotGrid shots={shots} onOpen={openPost} />
      ) : (
        <Missing>No finished post carries this look yet.</Missing>
      )}

      {material.length ? (
        <>
          <h3 className="mb-2 mt-6 text-sm font-semibold text-tx">
            Made from <span className="font-normal text-tx3">· {material.length} photos and work files</span>
          </h3>
          <ShotGrid shots={material} onOpen={openPost} limit={12} />
        </>
      ) : null}

      {hasDetails ? (
        <div className="mt-6">
          <button type="button" className="text-sm font-semibold text-ac" onClick={() => setMore(!more)}>
            {more ? 'Hide the rules' : 'Rules, colours, fonts and checks'}
          </button>
          {more ? (
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              {fixed.length ? (
                <Field label="Fixed to the style">
                  <ul className="w-full space-y-1">
                    {fixed.map(([k, v]) => (
                      <li key={k}>
                        <span className="font-semibold capitalize text-tx">{k.replace(/_/g, ' ')}</span> — {v}
                      </li>
                    ))}
                  </ul>
                </Field>
              ) : null}
              {colours.length || fonts.length ? (
                <Field label="Colours and fonts: from the brand, or set by the style">
                  <div className="w-full space-y-1">
                    {colours.map(([k, row]) => (
                      <p key={k} className="flex flex-wrap items-center gap-2">
                        {row.hex ? <span className="h-4 w-4 rounded border border-white/20" style={{ background: row.hex }} /> : null}
                        <span className="font-semibold text-tx">{k.replace(/_/g, ' ')}</span>
                        <Badge tone={row.from === 'brand' ? 'blue' : 'gold'}>{row.from}</Badge>
                        {row.role}
                      </p>
                    ))}
                    {fonts.map(([k, row]) => (
                      <p key={k} className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-tx">{k} font</span>
                        <Badge tone={row.from === 'brand' ? 'blue' : 'gold'}>{row.from}</Badge>
                        {row.family || row.role}
                      </p>
                    ))}
                  </div>
                </Field>
              ) : null}
              {style.checks?.length ? (
                <Field label="Checks">
                  <ul className="w-full list-disc space-y-0.5 pl-5">
                    {style.checks.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </Field>
              ) : null}
              {style.references?.length ? (
                <Field label="References">
                  <ul className="w-full space-y-1">
                    {style.references.map((r) => (
                      <li key={r.label}>
                        <span className="text-tx">{r.label}</span>
                        {r.note ? <span className="text-tx3"> — {r.note}</span> : null}
                      </li>
                    ))}
                  </ul>
                </Field>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Panel>
  )
}

function TemplateDetail({
  tpl,
  ctx,
  onClose,
  openPost,
}: {
  tpl: TaxonomyTemplateRow
  ctx: Ctx
  onClose: () => void
  openPost: (p: TaxonomyPost) => void
}) {
  const made = ctx.shotsByTemplate.get(tpl.template_id) || []
  const urls = (tpl.preview_urls || []).map((u) => resolveAssetUrl(u)).filter(Boolean)
  const types = ctx.typesByTemplate.get(tpl.template_id) || []
  const [big, setBig] = useState('')
  const [md, setMd] = useState(false)
  return (
    <Panel
      title={tpl.label || tpl.name}
      kicker={`Template · ${brandLabel(tpl.brand || '')}`}
      onClose={onClose}
      actions={<ApprovalButton section="templates" id={tpl.template_id} approval={tpl.approval} onDone={ctx.reload} />}
    >
      {tpl.description ? <p className="mb-4 text-sm text-tx2">{tpl.description}</p> : null}
      {urls.length ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {urls.map((u) => (
            <button key={u} type="button" onClick={() => setBig(u)}>
              <img src={u} alt="" loading="lazy" className="aspect-[4/5] w-full rounded-xl bg-bg2 object-cover" />
            </button>
          ))}
        </div>
      ) : (
        <Missing>No render or reference found for this template.</Missing>
      )}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Post type">
          {types.length ? (
            types.map((t) => <Chip key={t.id} label={t.name} onClick={() => ctx.go('types', t.id)} />)
          ) : (
            <Missing>no type lists it yet</Missing>
          )}
        </Field>
        <Field label="Canvas and photo">
          {tpl.canvas ? <Badge tone="mute">{tpl.canvas}</Badge> : null}
          <Badge tone={tpl.needs_photo ? 'gold' : 'green'}>{tpl.needs_photo ? 'Needs a photo' : 'Compose only'}</Badge>
          {tpl.status ? <Badge tone="mute">{tpl.status}</Badge> : null}
        </Field>
      </div>
      <h3 className="mb-2 mt-6 text-sm font-semibold text-tx">
        Posts made from it <span className="font-normal text-tx3">· {made.length} pictures</span>
      </h3>
      {made.length ? (
        <ShotGrid shots={made} onOpen={openPost} limit={12} />
      ) : (
        <Missing>No post found that uses this layout.</Missing>
      )}
      {tpl.template_md_excerpt ? (
        <div className="mt-4">
          <button type="button" className="text-sm font-semibold text-ac" onClick={() => setMd(!md)}>
            {md ? 'Hide spec notes' : 'Spec notes'}
          </button>
          {md ? <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-bg2 p-3 text-xs text-tx2">{tpl.template_md_excerpt}</pre> : null}
        </div>
      ) : null}
      {big ? <Lightbox src={big} onClose={() => setBig('')} /> : null}
    </Panel>
  )
}

function PostDetail({ post, ctx, onClose }: { post: TaxonomyPost; ctx: Ctx; onClose: () => void }) {
  const pics = post.pictures || []
  const [i, setI] = useState(0)
  const [lb, setLb] = useState('')
  const cur = pics[i]
  // every field below describes the picture that is open, because one post can hold several looks
  const styleIds = cur ? cur.styles || [] : post.style_ids || []
  const styles = styleIds.map((id) => ctx.styleById.get(id)).filter((s): s is TaxonomyStyle => !!s)
  const tplId = cur?.template || post.template_id || ''
  const tpl = tplId ? ctx.templateById.get(tplId) : undefined
  const typeId = cur?.type || (!cur ? post.type_ids?.[0] : '') || ''
  const type = typeId ? ctx.typeById.get(typeId) : undefined
  const sources: Shot[] = (cur?.sources || [])
    .map((s) => {
      const from = ctx.postById.get(s.post)
      const pic = from?.pictures?.find((x) => x.thumb === s.thumb)
      return from && pic ? { post: from, pic } : null
    })
    .filter((x): x is Shot => !!x)
  const usedIn = cur ? ctx.usedIn.get(cur.thumb) || [] : []
  const finished = !cur || finishedPic(cur)
  const openOther = (p: TaxonomyPost) => ctx.go('posts', p.id)
  const methodIds = Array.from(new Set(styles.map((s) => s.method_id).filter((m): m is string => !!m)))
  return (
    <Panel
      title={post.title || post.id}
      kicker={`${cur?.kind ? KIND_LABEL[cur.kind] : 'Post'} · ${brandLabel(post.brand)}`}
      onClose={onClose}
      actions={<ApprovalButton section="posts" id={post.id} approval={post.approval} onDone={ctx.reload} />}
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div>
          {cur ? (
            <>
              <button type="button" onClick={() => setLb(designMediaUrl(cur.mid || cur.thumb))} className="block w-full">
                <Pic pic={cur} size="mid" className="max-h-[70vh] w-full rounded-xl object-contain" />
              </button>
              {pics.length > 1 ? (
                <div className="mt-2 flex gap-2 overflow-x-auto">
                  {pics.map((p, k) => (
                    <button
                      key={p.thumb}
                      type="button"
                      onClick={() => setI(k)}
                      className={`shrink-0 overflow-hidden rounded-lg border ${k === i ? 'border-ac' : 'border-white/10'}`}
                    >
                      <Pic pic={p} className="h-20 w-16" />
                      <span className="block bg-black/40 text-center text-[10px] text-tx2">{p.role}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <div className="grid aspect-[4/5] place-items-center rounded-xl border border-dashed border-white/15 px-6 text-center text-sm text-tx3">
              No picture file for this post. The index only has a calendar or idea row.
            </div>
          )}
        </div>
        <div className="space-y-4">
          <Field label="Style">
            {styles.length ? (
              styles.map((s) => {
                const sp = (ctx.shotsByStyle.get(s.id) || [])[0]
                return (
                  <Chip
                    key={s.id}
                    label={s.name}
                    hint={`${(ctx.shotsByStyle.get(s.id) || []).length} pictures`}
                    thumb={sp ? <Pic pic={sp.pic} className="h-full w-full" /> : undefined}
                    onClick={() => ctx.go('styles', s.id)}
                  />
                )
              })
            ) : (
              <Missing>{finished ? 'no named look yet' : 'not a finished post'}</Missing>
            )}
          </Field>
          {finished ? (
            <>
              <Field label="Post type">
                {type ? <Chip label={type.name} hint={type.meaning} onClick={() => ctx.go('types', type.id)} /> : <Missing>no type fits</Missing>}
              </Field>
              <Field label="Template">
                {tpl ? (
                  <Chip
                    label={tpl.label}
                    hint={post.template_recorded === 'live' ? 'recorded by Campaign OS' : 'same layout, read from the picture'}
                    thumb={<img src={tplPic(tpl)} alt="" className="h-full w-full object-cover" />}
                    onClick={() => ctx.go('templates', tpl.template_id)}
                  />
                ) : tplId ? (
                  <Chip label={tplId} hint="recorded by Campaign OS, not in the template gallery" />
                ) : (
                  <Missing>no template, made by script or by hand</Missing>
                )}
              </Field>
              <Field label="Made with">
                {methodIds.length ? (
                  methodIds.map((m) => {
                    const mm = ctx.methodById.get(m)
                    return mm ? <Chip key={m} label={mm.name} hint="via its style" onClick={() => ctx.go('methods', m)} /> : null
                  })
                ) : (
                  <Missing>not recorded</Missing>
                )}
              </Field>
            </>
          ) : null}
          {sources.length || finished ? (
            <Field label="Started from">
              {sources.length ? <Thumbs shots={sources} onOpen={openOther} /> : <Missing>source photo not found yet</Missing>}
            </Field>
          ) : null}
          {usedIn.length ? (
            <Field label={`Used in ${usedIn.length} finished pictures`}>
              <Thumbs shots={usedIn} onOpen={openOther} />
            </Field>
          ) : null}
          <Field label="Where it is">
            <Badge tone="mute">{post.status}</Badge>
            {post.campaign ? <Badge tone="mute">{post.campaign}</Badge> : null}
            {post.date ? <Badge tone="mute">{post.date}</Badge> : null}
            {(post.sources || []).map((s) => (
              <Badge key={s} tone="blue">
                {s.replace(/_/g, ' ')}
              </Badge>
            ))}
          </Field>
          {cur ? <p className="break-all font-mono text-[11px] text-tx3">{cur.where}</p> : null}
          {post.breakdown ? (
            <p className="text-xs text-tx3">
              Style, type and template were read from the picture on {post.breakdown.at}. Not approved yet.
            </p>
          ) : null}
          {post.caption ? <p className="whitespace-pre-line rounded-xl bg-bg2 p-3 text-sm text-tx2">{post.caption}</p> : null}
        </div>
      </div>
      {lb ? <Lightbox src={lb} onClose={() => setLb('')} /> : null}
    </Panel>
  )
}

function TypeDetail({
  type,
  ctx,
  onClose,
  openPost,
}: {
  type: TaxonomyType
  ctx: Ctx
  onClose: () => void
  openPost: (p: TaxonomyPost) => void
}) {
  const shots = ctx.shotsByType.get(type.id) || []
  const brands = Array.from(new Set([...Object.keys(type.templates || {}), ...shots.map((sh) => sh.post.brand).filter(Boolean)]))
  return (
    <Panel
      title={type.name}
      kicker="Post type"
      onClose={onClose}
      actions={<ApprovalButton section="types" id={type.id} approval={type.approval} onDone={ctx.reload} />}
    >
      <p className="mb-4 text-sm text-tx2">
        {type.meaning} · {type.needs_photo ? 'needs a photo' : 'no photo needed'} · {shots.length} pictures
      </p>
      {brands.map((brand) => {
        const ids = type.templates?.[brand] || []
        const mine = shots.filter((sh) => sh.post.brand === brand)
        return (
          <div key={brand} className="mb-6">
            <h3 className="mb-2 text-sm font-semibold text-tx">
              {brandLabel(brand)} <span className="font-normal text-tx3">· {mine.length} pictures</span>
            </h3>
            {ids.length ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {ids.map((id) => {
                  const t = ctx.templateById.get(id)
                  return (
                    <Chip
                      key={id}
                      label={t?.label || id}
                      hint="template"
                      thumb={t && tplPic(t) ? <img src={tplPic(t)} alt="" className="h-full w-full object-cover" /> : undefined}
                      onClick={t ? () => ctx.go('templates', id) : undefined}
                    />
                  )
                })}
              </div>
            ) : (
              <p className="mb-3">
                <Missing>no template for {brandLabel(brand)} yet</Missing>
              </p>
            )}
            {mine.length ? <ShotGrid shots={mine} onOpen={openPost} limit={12} /> : <Missing>no post of this type found for {brandLabel(brand)}</Missing>}
          </div>
        )
      })}
    </Panel>
  )
}

function MethodDetail({
  method,
  ctx,
  onClose,
  openPost,
}: {
  method: TaxonomyMethod
  ctx: Ctx
  onClose: () => void
  openPost: (p: TaxonomyPost) => void
}) {
  const styles = (ctx.data.styles || []).filter((s) => s.method_id === method.id)
  return (
    <Panel
      title={method.name}
      kicker="Method"
      onClose={onClose}
      actions={<ApprovalButton section="methods" id={method.id} approval={method.approval} onDone={ctx.reload} />}
    >
      <p className="mb-1 text-sm text-tx2">{method.cost_notes}</p>
      {method.tools?.length ? <p className="mb-4 text-sm text-tx3">Tools: {method.tools.join(', ')}</p> : null}
      {styles.length ? (
        styles.map((s) => {
          const posts = (ctx.postsByStyle.get(s.id) || []).filter(pictured)
          return (
            <div key={s.id} className="mb-5">
              <button type="button" onClick={() => ctx.go('styles', s.id)} className="mb-2 text-sm font-semibold text-ac">
                {s.name} →
              </button>
              {posts.length ? <PostGrid posts={posts} onOpen={openPost} limit={12} /> : <Missing>no pictures for this style yet</Missing>}
            </div>
          )
        })
      ) : (
        <Missing>No seeded style uses this method.</Missing>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------- page

export function DesignTaxonomy() {
  const [params, setParams] = useSearchParams()
  const section = (params.get('section') as SectionKey) || 'styles'
  const openId = params.get('id') || ''
  const [stack, setStack] = useState<Stack>('not_approved')
  const [brand, setBrand] = useState('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState<TaxonomyPayload | null>(null)
  const [q, setQ] = useState('')
  const [styleFilter, setStyleFilter] = useState('')
  const [onlyPics, setOnlyPics] = useState(true)
  const [format, setFormat] = useState<Format>('all')
  const [show, setShow] = useState<'posts' | 'material' | 'all'>('posts')
  const [typeFilter, setTypeFilter] = useState('')
  const [tplFilter, setTplFilter] = useState('')
  const [page, setPage] = useState(0)

  const load = useCallback(() => {
    fetchDesignTaxonomy()
      .then((payload) => {
        if (payload.error && !payload.styles?.length) setError(payload.error)
        setData(payload)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])

  const go: Nav = useCallback(
    (sec, id) => {
      const next = new URLSearchParams(params)
      next.set('section', sec)
      if (id) next.set('id', id)
      else next.delete('id')
      setParams(next)
    },
    [params, setParams],
  )
  const closePanel = useCallback(() => go(section, ''), [go, section])
  const openPost = useCallback((p: TaxonomyPost) => go('posts', p.id), [go])

  const ctx = useMemo<Ctx | null>(() => {
    if (!data) return null
    const styleById = new Map((data.styles || []).map((s) => [s.id, s]))
    const methodById = new Map((data.methods || []).map((m) => [m.id, m]))
    const templateById = new Map((data.templates || []).map((t) => [t.template_id, t]))
    const postsByStyle = new Map<string, TaxonomyPost[]>()
    for (const p of data.posts || []) {
      for (const sid of p.style_ids || []) postsByStyle.set(sid, [...(postsByStyle.get(sid) || []), p])
    }
    const STATUS_RANK: Record<string, number> = {
      'approved on a review page (not lodged)': 0,
      lodged: 1,
      scheduled: 1,
      sent: 1,
      candidate: 2,
      draft: 3,
    }
    const postById = new Map((data.posts || []).map((p) => [p.id, p]))
    const typeById = new Map((data.types || []).map((t) => [t.id, t]))
    // every picture once: finished posts apart from the photos and work files they are made from
    const finished: Shot[] = []
    const material: Shot[] = []
    const seenPic = new Set<string>()
    const ranked = [...(data.posts || [])].sort((a, b) => (STATUS_RANK[a.status] ?? 4) - (STATUS_RANK[b.status] ?? 4))
    for (const post of ranked) {
      for (const pic of post.pictures || []) {
        if (seenPic.has(pic.thumb)) continue
        seenPic.add(pic.thumb)
        if (pic.kind === 'sheet') continue
        ;(finishedPic(pic) ? finished : material).push({ post, pic })
      }
    }
    const byRole = (a: Shot, b: Shot) => (ROLE_RANK[a.pic.role] ?? 1) - (ROLE_RANK[b.pic.role] ?? 1)
    finished.sort(byRole)
    const push = (map: Map<string, Shot[]>, key: string, shot: Shot) => map.set(key, [...(map.get(key) || []), shot])
    const shotsByStyle = new Map<string, Shot[]>()
    const materialByStyle = new Map<string, Shot[]>()
    const shotsByType = new Map<string, Shot[]>()
    const shotsByTemplate = new Map<string, Shot[]>()
    const usedIn = new Map<string, Shot[]>()
    for (const [sid, pins] of Object.entries(data.style_pins || {})) {
      for (const pin of pins) {
        const post = postById.get(pin.post)
        const pic = post?.pictures?.find((x) => x.thumb === pin.thumb)
        if (post && pic && !(shotsByStyle.get(sid) || []).some((x) => x.pic.thumb === pic.thumb)) push(shotsByStyle, sid, { post, pic })
      }
    }
    for (const shot of finished) {
      for (const sid of shot.pic.styles || []) {
        if (!(shotsByStyle.get(sid) || []).some((x) => x.pic.thumb === shot.pic.thumb)) push(shotsByStyle, sid, shot)
      }
      if (shot.pic.type) push(shotsByType, shot.pic.type, shot)
      const tplId = shot.pic.template || shot.post.template_id
      if (tplId) push(shotsByTemplate, tplId, shot)
      for (const src of shot.pic.sources || []) push(usedIn, src.thumb, shot)
    }
    for (const shot of material) for (const sid of shot.pic.styles || []) push(materialByStyle, sid, shot)
    const typesByTemplate = new Map<string, TaxonomyType[]>()
    for (const t of data.types || []) {
      for (const ids of Object.values(t.templates || {})) {
        for (const id of ids) typesByTemplate.set(id, [...(typesByTemplate.get(id) || []), t])
      }
    }
    return {
      data,
      go,
      reload: load,
      styleById,
      methodById,
      templateById,
      postsByStyle,
      shotsByStyle,
      typesByTemplate,
      typeById,
      postById,
      materialByStyle,
      shotsByType,
      shotsByTemplate,
      usedIn,
    }
  }, [data, go, load])

  const inStack = useCallback(
    <T extends { approval: { status: string } }>(rows: T[]) =>
      rows.filter((r) => (stack === 'approved' ? r.approval.status === 'approved' : r.approval.status !== 'approved')),
    [stack],
  )
  const brandOk = useCallback((b?: string) => brand === 'all' || (b || '') === brand, [brand])

  const styles = useMemo(
    () =>
      [...inStack(data?.styles || [])].sort(
        (a, b) => (ctx?.shotsByStyle.get(b.id)?.length || 0) - (ctx?.shotsByStyle.get(a.id)?.length || 0),
      ),
    [data?.styles, inStack, ctx],
  )
  const types = useMemo(() => inStack(data?.types || []), [data?.types, inStack])
  const methods = useMemo(() => inStack(data?.methods || []), [data?.methods, inStack])
  const templates = useMemo(
    () => inStack(data?.templates || []).filter((t) => brandOk(t.brand)),
    [data?.templates, inStack, brandOk],
  )
  const allPosts = useMemo(
    () => inStack(data?.posts || []).filter((p) => brandOk(p.brand)),
    [data?.posts, inStack, brandOk],
  )
  const posts = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return allPosts.filter((p) => {
      if (onlyPics && !pictured(p)) return false
      if (show === 'posts' && !finishedPost(p)) return false
      if (show === 'material' && finishedPost(p)) return false
      if (typeFilter && !p.type_ids?.includes(typeFilter)) return false
      if (tplFilter && p.template_id !== tplFilter && !p.pictures?.some((x) => x.template === tplFilter)) return false
      if (format !== 'all' && !p.pictures?.some(FORMAT_PIC[format])) return false
      if (styleFilter === 'none' && p.style_ids?.length) return false
      if (styleFilter && styleFilter !== 'none' && !p.style_ids?.includes(styleFilter)) return false
      if (needle && !`${p.title} ${p.campaign} ${p.style} ${p.status}`.toLowerCase().includes(needle)) return false
      return true
    })
  }, [allPosts, q, styleFilter, onlyPics, format, show, typeFilter, tplFilter])

  const PAGE_SIZE = 96
  const pageCount = Math.max(1, Math.ceil(posts.length / PAGE_SIZE))
  const pagePosts = useMemo(
    () =>
      [...posts]
        // posts from the live calendar first, then everything else that has a picture
        .sort((a, b) => Number(pictured(b)) - Number(pictured(a)) || Number(!!b.live) - Number(!!a.live))
        .slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [posts, page],
  )
  useEffect(() => setPage(0), [q, styleFilter, onlyPics, format, brand, stack, show, typeFilter, tplFilter])

  const tileLabel = useCallback(
    (_post: TaxonomyPost, pic: TaxonomyPicture) => {
      if (pic.kind && pic.kind !== 'post') return KIND_LABEL[pic.kind]
      const look = (pic.styles || []).map((id) => ctx?.styleById.get(id)?.name || id).join(' · ')
      const type = pic.type ? ctx?.typeById.get(pic.type)?.name || pic.type : ''
      return [look, type].filter(Boolean).join(' · ')
    },
    [ctx],
  )

  const count = (k: SectionKey) =>
    ({ styles: styles.length, templates: templates.length, types: types.length, posts: allPosts.length, methods: methods.length })[k]

  const btn = (on: boolean, color = 'bg-ac') =>
    `rounded-xl px-4 py-2 text-sm font-semibold ${on ? `${color} text-bg` : 'border border-white/15 text-tx2 hover:bg-white/5'}`

  // the open card is read from the URL, so Back closes it and a link can be shared
  const find = <T extends { id: string }>(rows?: T[]) => (rows || []).find((r) => r.id === openId)
  const openStyle = section === 'styles' ? find(data?.styles) : undefined
  const openType = section === 'types' ? find(data?.types) : undefined
  const openMethod = section === 'methods' ? find(data?.methods) : undefined
  const openPostRow = section === 'posts' ? find(data?.posts) : undefined
  const openTemplate = section === 'templates' ? (data?.templates || []).find((t) => t.template_id === openId) : undefined

  return (
    <div className="space-y-5">
      <PageIntro icon={Palette} badge="Design taxonomy" here="/design" title="Taxonomy of Design">
        Every look, template and post type, shown by the posts that use it. Open a post to see its look, its type,
        its template and the photo it started from.
      </PageIntro>

      <div className="flex flex-wrap gap-2">
        {SECTIONS.map((tab) => (
          <button key={tab.key} type="button" onClick={() => go(tab.key, '')} className={btn(section === tab.key)}>
            {tab.label} <span className="opacity-70">{data ? count(tab.key) : ''}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setStack('not_approved')} className={btn(stack === 'not_approved')}>
          Not approved yet
        </button>
        <button type="button" onClick={() => setStack('approved')} className={btn(stack === 'approved', 'bg-green')}>
          Approved
        </button>
        {section === 'posts' || section === 'templates' ? (
          <select
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            className="ml-auto rounded-xl border border-white/15 bg-bg2 px-3 py-2 text-sm text-tx"
            aria-label="Brand"
          >
            {BRANDS.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </select>
        ) : null}
      </div>

      {section === 'posts' ? (
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-tx3" />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setPage(0)
              }}
              placeholder="Search title, campaign, status"
              className="w-64 rounded-xl border border-white/15 bg-bg2 py-2 pl-9 pr-3 text-sm text-tx"
            />
          </label>
          <select
            value={styleFilter}
            onChange={(e) => setStyleFilter(e.target.value)}
            className="rounded-xl border border-white/15 bg-bg2 px-3 py-2 text-sm text-tx"
            aria-label="Style"
          >
            <option value="">Every style</option>
            <option value="none">No style yet</option>
            {(data?.styles || []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-xl border border-white/15 bg-bg2 px-3 py-2 text-sm text-tx"
            aria-label="Post type"
          >
            <option value="">Every type</option>
            {(data?.types || []).map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            value={tplFilter}
            onChange={(e) => setTplFilter(e.target.value)}
            className="rounded-xl border border-white/15 bg-bg2 px-3 py-2 text-sm text-tx"
            aria-label="Template"
          >
            <option value="">Every template</option>
            {(data?.templates || [])
              .filter((t) => ctx?.shotsByTemplate.get(t.template_id)?.length)
              .map((t) => (
                <option key={`${t.brand}-${t.template_id}`} value={t.template_id}>
                  {t.label}
                </option>
              ))}
          </select>
          <label className="flex items-center gap-2 text-sm text-tx2">
            <input type="checkbox" checked={onlyPics} onChange={(e) => setOnlyPics(e.target.checked)} />
            Only with a picture
          </label>
          <div className="flex gap-1" role="group" aria-label="Show">
            {(
              [
                ['posts', 'Finished posts'],
                ['material', 'Photos and work files'],
                ['all', 'Everything'],
              ] as ['posts' | 'material' | 'all', string][]
            ).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setShow(k)} className={btn(show === k)}>
                {label}
              </button>
            ))}
          </div>
          <div className="flex gap-1" role="group" aria-label="Format">
            {(
              [
                ['all', 'All formats'],
                ['static', 'Static posts'],
                ['story', 'Stories'],
                ['reel', 'Reels'],
              ] as [Format, string][]
            ).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setFormat(k)} className={btn(format === k)}>
                {label}
              </button>
            ))}
          </div>
          <p className="w-full text-sm text-tx3">
            Showing {posts.length} of {allPosts.length}.
          </p>
        </div>
      ) : null}

      {loading ? <div className="h-40 animate-pulse rounded-2xl bg-bg3" /> : null}
      {error ? <p className="rounded-2xl border border-red/30 bg-red/5 px-4 py-3 text-sm text-red">{error}</p> : null}

      {ctx && section === 'styles' ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {styles.map((s) => {
            const shots = ctx.shotsByStyle.get(s.id) || []
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => go('styles', s.id)}
                className="glass flex flex-col gap-3 rounded-2xl border border-white/10 p-3 text-left transition hover:border-ac/50"
              >
                <Mosaic shots={shots} empty="No finished post carries this look yet" />
                <div className="flex items-baseline justify-between gap-2">
                  <p className="font-display text-lg font-semibold text-tx">{s.name}</p>
                  <p className="shrink-0 text-sm text-tx3">{shots.length} pictures</p>
                </div>
                <div className="flex flex-wrap gap-1">
                  {Array.from(new Set(shots.map((sh) => sh.post.brand).filter(Boolean))).map((b) => (
                    <Badge key={b} tone="mute">
                      {brandLabel(b)}
                    </Badge>
                  ))}
                  {s.candidate ? <Badge tone="gold">new name</Badge> : null}
                </div>
              </button>
            )
          })}
          {!styles.length ? <p className="text-sm text-tx3">Nothing in this stack.</p> : null}
        </div>
      ) : null}

      {ctx && section === 'templates' ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {templates.map((t) => {
            const src = tplPic(t)
            return (
              <button
                key={`${t.brand}-${t.template_id}`}
                type="button"
                onClick={() => go('templates', t.template_id)}
                className="glass overflow-hidden rounded-2xl border border-white/10 text-left transition hover:border-ac/50"
              >
                {src ? (
                  <img src={src} alt="" loading="lazy" className="aspect-[4/5] w-full bg-bg2 object-cover" />
                ) : (
                  <div className="grid aspect-[4/5] place-items-center bg-bg2 text-xs text-tx3">No preview</div>
                )}
                <div className="space-y-1 p-3">
                  <p className="font-semibold text-tx">{t.label}</p>
                  <div className="flex flex-wrap gap-1">
                    <Badge tone="mute">{brandLabel(t.brand || '')}</Badge>
                    {ctx.shotsByTemplate.get(t.template_id)?.length ? (
                      <Badge tone="green">{ctx.shotsByTemplate.get(t.template_id)?.length} posts</Badge>
                    ) : null}
                    {(ctx.typesByTemplate.get(t.template_id) || []).map((ty) => (
                      <Badge key={ty.id} tone="blue">
                        {ty.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              </button>
            )
          })}
          {!templates.length ? <p className="text-sm text-tx3">Nothing in this stack.</p> : null}
        </div>
      ) : null}

      {ctx && section === 'types' ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {types.map((ty) => {
            const shots = ctx.shotsByType.get(ty.id) || []
            return (
              <button
                key={ty.id}
                type="button"
                onClick={() => go('types', ty.id)}
                className="glass flex flex-col gap-3 rounded-2xl border border-white/10 p-3 text-left transition hover:border-ac/50"
              >
                <Mosaic shots={shots} empty="No post of this type found yet" />
                <div>
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="font-display text-lg font-semibold text-tx">{ty.name}</p>
                    <p className="shrink-0 text-sm text-tx3">{shots.length} pictures</p>
                  </div>
                  <p className="text-sm text-tx3">{ty.meaning}</p>
                </div>
              </button>
            )
          })}
          {!types.length ? <p className="text-sm text-tx3">Nothing in this stack.</p> : null}
        </div>
      ) : null}

      {ctx && section === 'methods' ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {methods.map((m) => {
            const shots = (ctx.data.styles || [])
              .filter((s) => s.method_id === m.id)
              .flatMap((s) => (ctx.shotsByStyle.get(s.id) || []).slice(0, 2))
            return (
              <button
                key={m.id}
                type="button"
                onClick={() => go('methods', m.id)}
                className="glass flex flex-col gap-3 rounded-2xl border border-white/10 p-3 text-left transition hover:border-ac/50"
              >
                <Mosaic shots={shots} empty="No pictures — no seeded style uses this method yet" />
                <div>
                  <p className="font-display text-lg font-semibold text-tx">{m.name}</p>
                  <p className="text-sm text-tx3">{m.cost_notes}</p>
                </div>
              </button>
            )
          })}
          {!methods.length ? <p className="text-sm text-tx3">Nothing in this stack.</p> : null}
        </div>
      ) : null}

      {ctx && section === 'posts' ? (
        <>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
            {pagePosts.map((p) => (
              <PostTile key={p.id} post={p} format={format} labelOf={tileLabel} onOpen={() => openPost(p)} />
            ))}
          </div>
          {pageCount > 1 ? (
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} className={`${btn(false)} disabled:opacity-40`}>
                Previous
              </button>
              {Array.from({ length: pageCount }, (_, i) => (
                <button key={i} type="button" onClick={() => setPage(i)} className={btn(i === page)}>
                  {i + 1}
                </button>
              ))}
              <button
                type="button"
                disabled={page >= pageCount - 1}
                onClick={() => setPage(page + 1)}
                className={`${btn(false)} disabled:opacity-40`}
              >
                Next
              </button>
              <span className="text-sm text-tx3">
                {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, posts.length)} of {posts.length}
              </span>
            </div>
          ) : null}
          {!posts.length ? <p className="text-sm text-tx3">Nothing matches.</p> : null}
        </>
      ) : null}

      {ctx && openStyle ? <StyleDetail style={openStyle} ctx={ctx} onClose={closePanel} openPost={openPost} /> : null}
      {ctx && openTemplate ? <TemplateDetail tpl={openTemplate} ctx={ctx} onClose={closePanel} openPost={openPost} /> : null}
      {ctx && openType ? <TypeDetail type={openType} ctx={ctx} onClose={closePanel} openPost={openPost} /> : null}
      {ctx && openMethod ? <MethodDetail method={openMethod} ctx={ctx} onClose={closePanel} openPost={openPost} /> : null}
      {ctx && openPostRow ? <PostDetail post={openPostRow} ctx={ctx} onClose={closePanel} /> : null}
    </div>
  )
}
