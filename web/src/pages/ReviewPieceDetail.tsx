import { ImageIcon, Pencil, RotateCcw } from 'lucide-react'
import { templateMetaFromInbox } from '../lib/templateMeta'
import { TemplateReferenceCompare } from '../components/TemplateReferenceCompare'
import { TemplateReferenceTag } from '../components/TemplateReferenceTag'
import { Tip } from '../components/ui'
import type { CampaignAsset, InboxItem } from '../lib/api'

export type ReviewPieceDetailProps = {
  item: InboxItem
  caption: string
  visualUrl: string | null
  visualBrief: string
  imgBroken: boolean
  asset: CampaignAsset | null
  assetLoading: boolean
  cid?: string
  aid?: string
  editingCaption: boolean
  captionDraft: string
  captionSaving: boolean
  drafting: boolean
  captionRegenerating: boolean
  regenerateDisabled: boolean
  regenerateTip: string
  onStartEditCaption: () => void
  onCancelEditCaption: () => void
  onCaptionDraftChange: (value: string) => void
  onSaveCaption: () => void
  onRegenerateCaption: () => void
  onRegenerate: () => void
  onImgBroken: () => void
}

export function ReviewPieceDetail({
  item,
  caption,
  visualUrl,
  visualBrief,
  imgBroken,
  asset,
  assetLoading,
  cid,
  aid,
  editingCaption,
  captionDraft,
  captionSaving,
  drafting,
  captionRegenerating,
  regenerateDisabled,
  regenerateTip,
  onStartEditCaption,
  onCancelEditCaption,
  onCaptionDraftChange,
  onSaveCaption,
  onRegenerateCaption,
  onRegenerate,
  onImgBroken,
}: ReviewPieceDetailProps) {
  const brandLabel = item.brand_id || 'brand'
  const templateMeta = templateMetaFromInbox(item)

  return (
    <div className="grid gap-6 md:grid-cols-2 md:items-start">
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="font-display text-lg font-semibold text-tx">Caption</h2>
          {!editingCaption ? (
            <div className="flex flex-wrap items-center gap-2">
              <Tip text="Edit the caption on this draft.">
                <button
                  type="button"
                  data-testid="edit-caption-btn"
                  title="Edit caption"
                  className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac"
                  onClick={onStartEditCaption}
                >
                  <Pencil className="h-4 w-4" strokeWidth={2.5} />
                  Edit caption
                </button>
              </Tip>
              <Tip text="Queue a fresh caption for this draft (keeps the current image).">
                <button
                  type="button"
                  data-testid="regenerate-caption-btn"
                  title="Regenerate caption"
                  disabled={captionRegenerating}
                  onClick={onRegenerateCaption}
                  className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RotateCcw className="h-4 w-4" />
                  {captionRegenerating ? 'Queuing…' : 'Regenerate caption'}
                </button>
              </Tip>
            </div>
          ) : null}
        </div>
        {editingCaption ? (
          <div className="space-y-2">
            <textarea
              data-testid="caption-editor"
              value={captionDraft}
              onChange={(e) => onCaptionDraftChange(e.target.value)}
              rows={6}
              className="w-full rounded-2xl border border-bd bg-bg2/50 px-3 py-2 text-sm text-tx"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="save-caption-btn"
                disabled={captionSaving}
                onClick={onSaveCaption}
                className="rounded-full bg-ac px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
              >
                {captionSaving ? 'Saving…' : 'Save'}
              </button>
              <button
                type="button"
                data-testid="cancel-caption-btn"
                disabled={captionSaving}
                onClick={onCancelEditCaption}
                className="rounded-full border border-bd px-4 py-2 text-sm font-semibold hover:border-red hover:text-red"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-tx2" data-testid="caption-display">
            {caption || 'No brief on this card yet.'}
          </p>
        )}
        {visualBrief ? (
          <p className="text-sm text-tx3">
            <span className="font-semibold uppercase tracking-wide text-[12px]">Visual brief</span>
            <br />
            {visualBrief}
          </p>
        ) : null}
      </div>

      <div className="space-y-3 md:col-span-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-lg font-semibold text-tx">Image</h2>
            <TemplateReferenceTag meta={templateMeta} preview="label-only" />
          </div>
          <Tip text={regenerateTip} block>
            <button
              type="button"
              data-testid="regenerate-btn"
              title={regenerateTip}
              disabled={regenerateDisabled || drafting}
              onClick={onRegenerate}
              className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              {drafting ? 'Drafting…' : 'Regenerate'}
            </button>
          </Tip>
        </div>
        {assetLoading && !asset ? (
          <div className="h-48 animate-pulse rounded-2xl bg-bg3" />
        ) : visualUrl && !imgBroken ? (
          <TemplateReferenceCompare
            draftUrl={visualUrl}
            draftAlt={asset?.name || 'Asset visual'}
            templateMeta={templateMeta}
            draftBroken={imgBroken}
            onDraftBroken={onImgBroken}
          />
        ) : imgBroken ? (
          <div className="rounded-2xl border border-bd bg-bg2/50 px-4 py-3 text-sm text-tx3">
            <p>
              Image URL unreachable — <code className="text-xs break-all">{visualUrl}</code>
            </p>
            <p className="mt-1">Use Regenerate when under the daily cap for {brandLabel}.</p>
          </div>
        ) : !cid || !aid || (asset && !visualUrl) ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-bd text-sm text-tx3">
            <ImageIcon className="h-8 w-8 opacity-50" />
            <p>No visual on file.</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}
