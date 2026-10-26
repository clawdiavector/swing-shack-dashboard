import { ImageIcon, Layers, Loader2, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrandSwitch, useBrand } from '../../components/BrandSwitch'
import { FilterChips, HeroPanel, PageIntro } from '../../components/chrome'
import { PlatformMock } from '../../components/PlatformMock'
import { Badge, QueueItemThumb, Tip } from '../../components/ui'
import {
  fetchPostStudioFields,
  fetchTemplateGallery,
  fetchVisualLibrary,
  lodgePostDraft,
  previewPostStudio,
  resolveAssetUrl,
  type PostStudioFieldSpec,
  type TemplateGalleryTemplate,
} from '../../lib/api'
import { actorName } from '../../lib/plan'
import { brandPhotoPath, defaultGoLiveDate, slugFromCaption } from '../../lib/postStudio'
import type { PlatformTab } from '../../lib/platformMock'

type VisualRow = {
  filename: string
  url?: string
  thumbnail_data_url?: string
  score?: number
}

const inputCls =
  'w-full rounded-xl border border-white/10 bg-bg2/80 px-3 py-2 text-sm text-tx placeholder:text-tx3 focus:border-ac focus:outline-none'

export function PostStudio() {
  const { brandId } = useBrand()
  const [templates, setTemplates] = useState<TemplateGalleryTemplate[]>([])
  const [templateId, setTemplateId] = useState('')
  const [photos, setPhotos] = useState<VisualRow[]>([])
  const [photoFile, setPhotoFile] = useState('')
  const [fieldSpecs, setFieldSpecs] = useState<PostStudioFieldSpec[]>([])
  const [fields, setFields] = useState<Record<string, string>>({})
  const [caption, setCaption] = useState('')
  const [slug, setSlug] = useState('')
  const [goLive, setGoLive] = useState(defaultGoLiveDate())
  const [previewTab, setPreviewTab] = useState<PlatformTab>('instagram')
  const [previewImages, setPreviewImages] = useState<Record<string, string>>({})
  const [needsPhoto, setNeedsPhoto] = useState(false)
  const [loadingGallery, setLoadingGallery] = useState(false)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [lodgeBusy, setLodgeBusy] = useState(false)
  const [toast, setToast] = useState<{ tone: 'green' | 'red'; text: string } | null>(null)
  const [reviewLink, setReviewLink] = useState('')

  const selectedTemplate = useMemo(
    () => templates.find((t) => (t.template_id || t.archetype_id) === templateId),
    [templates, templateId],
  )

  useEffect(() => {
    if (!brandId) return
    setLoadingGallery(true)
    setTemplateId('')
    setPhotoFile('')
    setPreviewImages({})
    Promise.all([
      fetchTemplateGallery(brandId),
      fetchVisualLibrary(brandId, 80),
    ])
      .then(([gallery, lib]) => {
        const rows =
          gallery.templates ||
          (gallery.sections || []).flatMap((s) => s.templates || [])
        setTemplates(rows)
        const imgs = (lib.images || []) as VisualRow[]
        setPhotos(imgs.filter((row) => !row.filename?.includes('.visual-dna')))
      })
      .catch(() => {
        setTemplates([])
        setPhotos([])
      })
      .finally(() => setLoadingGallery(false))
  }, [brandId])

  useEffect(() => {
    if (!brandId || !templateId) {
      setFieldSpecs([])
      return
    }
    fetchPostStudioFields(brandId, templateId)
      .then((res) => {
        const specs = res.fields || []
        setFieldSpecs(specs)
        setNeedsPhoto(Boolean(selectedTemplate?.needs_photo))
        setFields((prev) => {
          const next = { ...prev }
          for (const spec of specs) {
            if (next[spec.key] === undefined) next[spec.key] = ''
          }
          return next
        })
      })
      .catch(() => setFieldSpecs([]))
  }, [brandId, templateId, selectedTemplate?.needs_photo])

  useEffect(() => {
    if (!slug && caption.trim()) {
      setSlug(slugFromCaption(caption))
    }
  }, [caption, slug])

  const previewImageUrl = useMemo(() => {
    const data = previewImages[previewTab] || previewImages.instagram || ''
    if (data.startsWith('data:')) return data
    return resolveAssetUrl(data)
  }, [previewImages, previewTab])

  const runPreview = useCallback(async () => {
    if (!brandId || !templateId) {
      setToast({ tone: 'red', text: 'Pick a brand and a template first.' })
      return
    }
    setPreviewBusy(true)
    setToast(null)
    try {
      const { status, data } = await previewPostStudio({
        brand: brandId,
        archetype: templateId,
        fields,
        photo: photoFile ? brandPhotoPath(brandId, photoFile) : undefined,
        channels: ['instagram', 'facebook'],
      })
      if (!data.ok || status !== 200) {
        setToast({ tone: 'red', text: data.error || 'Preview failed.' })
        setPreviewImages({})
        return
      }
      setPreviewImages(data.images || {})
      setNeedsPhoto(Boolean(data.needs_photo))
      if (data.field_specs?.length) setFieldSpecs(data.field_specs)
      setPreviewTab('instagram')
    } catch (e) {
      setToast({ tone: 'red', text: e instanceof Error ? e.message : 'Preview failed.' })
    } finally {
      setPreviewBusy(false)
    }
  }, [brandId, templateId, fields, photoFile])

  const lodgeDraft = async () => {
    if (!brandId || !templateId) {
      setToast({ tone: 'red', text: 'Pick a brand and template.' })
      return
    }
    if (!caption.trim()) {
      setToast({ tone: 'red', text: 'Write a caption before lodging.' })
      return
    }
    const name = actorName()
    if (!name) {
      setToast({ tone: 'red', text: 'Type your name when asked so the calendar can record who lodged it.' })
      return
    }
    const useSlug = (slug || slugFromCaption(caption)).trim()
    if (!useSlug) {
      setToast({ tone: 'red', text: 'Choose a short slug for this post.' })
      return
    }
    setLodgeBusy(true)
    setToast(null)
    setReviewLink('')
    try {
      const { status, data } = await lodgePostDraft(
        {
          brand: brandId,
          slug: useSlug,
          date: goLive,
          caption: caption.trim(),
          archetype: templateId,
          fields,
          photo: photoFile ? brandPhotoPath(brandId, photoFile) : undefined,
        },
        name,
      )
      if (!data.ok || status !== 200) {
        setToast({ tone: 'red', text: data.error || 'Could not lodge the draft.' })
        return
      }
      setToast({
        tone: 'green',
        text: data.next_action
          ? `${data.next_action} — open Review to approve when ready.`
          : 'Draft lodged. Approve it from Review when you are happy.',
      })
      const href = data.links?.review
      if (href) setReviewLink(href)
    } catch (e) {
      setToast({ tone: 'red', text: e instanceof Error ? e.message : 'Could not lodge the draft.' })
    } finally {
      setLodgeBusy(false)
    }
  }

  const templateSections = useMemo(() => {
    const map = new Map<string, TemplateGalleryTemplate[]>()
    for (const t of templates) {
      const sec = t.section || 'Other'
      if (!map.has(sec)) map.set(sec, [])
      map.get(sec)!.push(t)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [templates])

  return (
    <div className="space-y-6">
      <PageIntro icon={Sparkles} badge="Studio" here="/create/post-studio" title="Post studio">
        Pick a measured template, optional photo, and caption. Preview the composed post, then lodge it as a
        draft. Approving and publishing stay in Review and Publish.
      </PageIntro>

      <div className="flex flex-wrap items-center gap-3">
        <BrandSwitch />
        {brandId ? <Badge tone="mute">{brandId}</Badge> : null}
      </div>

      {toast ? (
        <p
          className={`rounded-2xl border px-4 py-3 text-sm ${
            toast.tone === 'green'
              ? 'border-green/40 bg-green/10 text-green'
              : 'border-red/40 bg-red/10 text-red'
          }`}
        >
          {toast.text}
          {reviewLink ? (
            <span className="mt-2 block">
              <Link to={reviewLink.replace(/^\/app/, '')} className="font-semibold text-ac underline">
                Open in Review
              </Link>
            </span>
          ) : null}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,1fr)]">
        <div className="space-y-6">
          <HeroPanel icon={Layers} kicker="Template" title="Choose a layout" meta="Deterministic compose — same template, same pixels every time.">
            {loadingGallery ? (
              <p className="text-sm text-tx3">Loading templates…</p>
            ) : !brandId ? (
              <p className="text-sm text-tx3">Select a brand to see its templates.</p>
            ) : (
              <div className="space-y-4 max-h-[28rem] overflow-y-auto pr-1">
                {templateSections.map(([section, rows]) => (
                  <div key={section}>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-tx3">{section}</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {rows.map((t) => {
                        const id = t.template_id || t.archetype_id || ''
                        const active = id === templateId
                        const thumb = resolveAssetUrl(t.preview_urls?.[0])
                        return (
                          <button
                            key={id}
                            type="button"
                            onClick={() => setTemplateId(id)}
                            className={`flex gap-3 rounded-xl border p-2 text-left transition ${
                              active ? 'border-ac bg-ac/10' : 'border-white/10 hover:border-white/20'
                            }`}
                          >
                            <div className="h-16 w-14 shrink-0 overflow-hidden rounded-lg bg-bg2">
                              {thumb ? (
                                <QueueItemThumb src={thumb} alt="" className="h-full w-full object-cover" />
                              ) : null}
                            </div>
                            <div className="min-w-0">
                              <p className="truncate text-sm font-semibold text-tx">{t.label}</p>
                              <p className="text-xs text-tx3">{t.needs_photo ? 'Needs photo' : 'Pack photo'}</p>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </HeroPanel>

          {(needsPhoto || selectedTemplate?.needs_photo) && brandId ? (
            <HeroPanel icon={ImageIcon} kicker="Photo" title="Product or venue still" meta="Only templates that need a library photo.">
              <div className="grid max-h-48 grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-6">
                {photos.map((p) => {
                  const thumb = p.thumbnail_data_url || resolveAssetUrl(p.url || '')
                  const active = photoFile === p.filename
                  return (
                    <button
                      key={p.filename}
                      type="button"
                      title={p.filename}
                      onClick={() => setPhotoFile(p.filename)}
                      className={`aspect-square overflow-hidden rounded-lg border-2 ${
                        active ? 'border-ac' : 'border-transparent'
                      }`}
                    >
                      {thumb ? <img src={thumb} alt="" className="h-full w-full object-cover" /> : null}
                    </button>
                  )
                })}
              </div>
            </HeroPanel>
          ) : null}

          {fieldSpecs.length ? (
            <HeroPanel icon={Sparkles} kicker="On-image copy" title="Template fields" meta="These lines render on the picture.">
              <div className="grid gap-3 sm:grid-cols-2">
                {fieldSpecs.map((spec) => (
                  <label key={spec.key} className="block space-y-1">
                    <span className="text-xs font-semibold uppercase tracking-wide text-tx3">
                      <Tip text={spec.hint || spec.key}>{spec.label || spec.key}</Tip>
                    </span>
                    <input
                      className={inputCls}
                      value={fields[spec.key] || ''}
                      onChange={(e) => setFields((prev) => ({ ...prev, [spec.key]: e.target.value }))}
                    />
                  </label>
                ))}
              </div>
            </HeroPanel>
          ) : null}

          <HeroPanel icon={Sparkles} kicker="Caption" title="Feed caption" meta="Lodged with the draft; edit again in Review.">
            <textarea
              className={`${inputCls} min-h-[120px]`}
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Write the Instagram / Facebook caption…"
            />
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="block space-y-1">
                <span className="text-xs font-semibold uppercase text-tx3">Go-live date</span>
                <input
                  type="date"
                  className={inputCls}
                  value={goLive}
                  onChange={(e) => setGoLive(e.target.value)}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs font-semibold uppercase text-tx3">Slug</span>
                <input
                  className={inputCls}
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="short-name-for-calendar"
                />
              </label>
            </div>
          </HeroPanel>

          <div className="flex flex-wrap gap-3">
            <Tip text="Compose a fresh preview without saving.">
              <button
                type="button"
                disabled={previewBusy || !templateId}
                onClick={() => void runPreview()}
                className="inline-flex items-center gap-1.5 rounded-full bg-yel px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
              >
                {previewBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {previewBusy ? 'Composing…' : 'Update preview'}
              </button>
            </Tip>
            <Tip text="Render on the server and land in Review as a draft — not approved.">
              <button
                type="button"
                disabled={lodgeBusy || !templateId}
                onClick={() => void lodgeDraft()}
                className="glass-pill inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-semibold text-tx hover:border-ac disabled:opacity-50"
              >
                {lodgeBusy ? 'Lodging…' : 'Lodge draft'}
              </button>
            </Tip>
          </div>
        </div>

        <div className="space-y-4">
          <FilterChips
            options={[
              { id: 'instagram', label: 'Instagram' },
              { id: 'facebook', label: 'Facebook' },
            ]}
            value={previewTab}
            onChange={(id) => setPreviewTab(id as PlatformTab)}
          />
          <PlatformMock
            platform={previewTab}
            imageUrl={previewImageUrl}
            caption={caption}
            brandId={brandId}
          />
          {!previewImageUrl && templateId ? (
            <p className="text-sm text-tx3">Tap Update preview to render this template.</p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
