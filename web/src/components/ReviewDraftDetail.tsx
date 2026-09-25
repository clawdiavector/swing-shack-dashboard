import { Check, Pencil, RotateCcw, Sparkles, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { InboxItem } from '../lib/api'
import { resolveAssetUrl } from '../lib/api'
import {
  briefSectionEntries,
  composedChannelKeys,
  composedUrlForChannel,
  draftHeadlineFromCaption,
  qcDisplayScore,
  qcReasonsList,
} from '../lib/reviewDraftMeta'
import { BrandChip } from './BrandChip'
import { Badge, PressIcon, Tip } from './ui'

export type ReviewDraftDetailProps = {
  item: InboxItem
  showBrandChip: boolean
  atImageCap: boolean
  regenerateTip: string
  busy: boolean
  onApprove: () => void
  onReject: (reason: string) => void
  onRegenerate: (note: string) => void
  onRecomposeHeadline: (headline: string) => void
  onSwapCandidate: (candidateIndex: number) => void
}

function channelLabel(id: string) {
  if (id === 'instagram') return 'Instagram'
  if (id === 'gbp') return 'GBP'
  return id.replace(/_/g, ' ')
}

export function ReviewDraftDetail({
  item,
  showBrandChip,
  atImageCap,
  regenerateTip,
  busy,
  onApprove,
  onReject,
  onRegenerate,
  onRecomposeHeadline,
  onSwapCandidate,
}: ReviewDraftDetailProps) {
  const channels = useMemo(() => composedChannelKeys(item), [item])
  const [activeChannel, setActiveChannel] = useState(
    () => channels[0] || item.meta?.primary_channel || 'instagram',
  )
  const composedUrl = composedUrlForChannel(item, activeChannel) || resolveAssetUrl(item.meta?.image_url)

  const qc = item.meta?.qc
  const qcVerdict = (qc?.verdict || 'pending').replace(/_/g, ' ')
  const qcScore = qcDisplayScore(qc)
  const qcReasons = qcReasonsList(qc)
  const selectedIndex = qc?.selected ?? 0
  const candidates = item.meta?.photo_candidates || []
  const briefSections = briefSectionEntries(item.meta?.brief?.sections)
  const refUsed = item.meta?.reference_used

  const [regenOpen, setRegenOpen] = useState(false)
  const [regenNote, setRegenNote] = useState('')
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [rejectErr, setRejectErr] = useState('')
  const [editingHeadline, setEditingHeadline] = useState(false)
  const [headlineDraft, setHeadlineDraft] = useState(() =>
    draftHeadlineFromCaption(item.meta?.caption),
  )

  function submitRegenerate() {
    const note = regenNote.trim()
    if (!note) return
    onRegenerate(note)
    setRegenOpen(false)
    setRegenNote('')
  }

  function submitReject() {
    const reason = rejectReason.trim()
    if (!reason) {
      setRejectErr('A reason is required before sending back.')
      return
    }
    setRejectErr('')
    onReject(reason)
    setRejectOpen(false)
    setRejectReason('')
  }

  function saveHeadline() {
    const next = headlineDraft.trim()
    if (!next) return
    onRecomposeHeadline(next)
    setEditingHeadline(false)
  }

  return (
    <section
      className="glass rounded-2xl border-[1.5px] border-ac/35 p-5 shadow-[0_0_0_3px_rgba(52,211,153,.08)] backdrop-blur-xl"
      data-testid="review-draft-detail"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] font-semibold tracking-wide text-tx3 uppercase">Next up</p>
          <h2 className="font-display text-xl font-semibold leading-snug text-tx">
            {item.title || item.summary || item.id}
          </h2>
        </div>
        <BrandChip brandId={item.brand_id} show={showBrandChip} />
      </div>

      <div className="mt-4 space-y-4">
        {channels.length > 1 ? (
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Composed channels">
            {channels.map((ch) => (
              <button
                key={ch}
                type="button"
                role="tab"
                aria-selected={activeChannel === ch}
                data-testid={`channel-tab-${ch}`}
                onClick={() => setActiveChannel(ch)}
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
                  activeChannel === ch
                    ? 'bg-ac text-bg'
                    : 'border border-bd text-tx2 hover:border-ac hover:text-ac'
                }`}
              >
                {channelLabel(ch)}
              </button>
            ))}
          </div>
        ) : null}

        <div className="overflow-hidden rounded-2xl border border-bd bg-bg2/30">
          {composedUrl ? (
            <img
              src={composedUrl}
              alt={`Composed ${activeChannel}`}
              className="min-h-[280px] w-full object-contain md:min-h-[480px]"
              data-testid="composed-preview"
            />
          ) : (
            <div
              className="flex min-h-[280px] items-center justify-center text-sm text-tx3 md:min-h-[480px]"
              data-testid="composed-preview-empty"
            >
              No composed preview yet
            </div>
          )}
        </div>

        {candidates.length ? (
          <div>
            <h3 className="font-display text-sm font-semibold text-tx">Photo candidates</h3>
            <ul className="mt-2 flex flex-wrap gap-3">
              {candidates.map((c, idx) => {
                const url = resolveAssetUrl(c.url || c.path || '')
                const isSelected = idx === selectedIndex
                return (
                  <li key={c.index ?? idx} className="flex flex-col items-center gap-1">
                    {url ? (
                      <img
                        src={url}
                        alt={`Candidate ${idx + 1}`}
                        className={`h-20 w-20 rounded-xl border object-cover ${isSelected ? 'border-ac ring-2 ring-ac/40' : 'border-bd'}`}
                      />
                    ) : (
                      <div className="h-20 w-20 rounded-xl border border-dashed border-bd bg-bg3" />
                    )}
                    {!isSelected ? (
                      <button
                        type="button"
                        data-testid={`swap-candidate-${idx}`}
                        disabled={busy}
                        onClick={() => onSwapCandidate(idx)}
                        className="text-xs font-semibold text-ac hover:underline disabled:opacity-50"
                      >
                        Swap
                      </button>
                    ) : (
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-tx3">Active</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}

        {briefSections.length ? (
          <div className="rounded-2xl border border-bd bg-bg2/20 px-3 py-2">
            <h3 className="font-display text-sm font-semibold text-tx">Brief</h3>
            <div className="mt-2 space-y-1">
              {briefSections.map((sec) => (
                <details key={sec.title} className="group rounded-xl border border-bd/60 bg-bg/40 px-3 py-2">
                  <summary className="cursor-pointer font-semibold text-sm text-tx2">{sec.title}</summary>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-tx3">{sec.body}</p>
                </details>
              ))}
            </div>
          </div>
        ) : null}

        {refUsed?.url || refUsed?.selected_because ? (
          <div className="flex flex-wrap items-start gap-3 rounded-2xl border border-bd px-3 py-2">
            {refUsed.url ? (
              <img
                src={resolveAssetUrl(refUsed.url)}
                alt="Reference"
                className="h-16 w-16 shrink-0 rounded-lg border border-bd object-cover"
                data-testid="reference-thumb"
              />
            ) : null}
            <div className="min-w-0 flex-1">
              <p className="font-display text-sm font-semibold text-tx">Why this reference</p>
              <p className="mt-1 text-sm text-tx2" data-testid="reference-why">
                {refUsed.selected_because || 'Matched brand visual DNA for this moment.'}
              </p>
            </div>
          </div>
        ) : null}

        <div
          className="flex flex-wrap items-center gap-2 rounded-2xl border border-bd px-3 py-2"
          data-testid="qc-badge"
        >
          <span className="font-display text-sm font-semibold text-tx">QC</span>
          <Badge tone={qc?.verdict === 'pass' ? 'green' : qc?.verdict === 'needs_human' ? 'gold' : 'mute'}>
            {qcVerdict}
          </Badge>
          {qcScore != null ? (
            <span className="text-xs text-tx3">
              Score <span className="font-semibold text-tx">{qcScore}</span>
            </span>
          ) : null}
          {qcReasons.length ? (
            <span className="text-xs text-tx3">{qcReasons.join(' · ')}</span>
          ) : null}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2 border-t border-bd pt-4" data-testid="review-draft-actions">
        <Tip text="Mark this approved. It will not go live.">
          <button
            type="button"
            data-testid="draft-approve-btn"
            disabled={busy}
            onClick={onApprove}
            className="inline-flex items-center gap-1.5 rounded-full bg-ac px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-50"
          >
            <Check className="h-4 w-4" strokeWidth={2.5} />
            Approve
          </button>
        </Tip>

        <Tip text={regenerateTip} block>
          <button
            type="button"
            data-testid="draft-regenerate-btn"
            title={regenerateTip}
            disabled={busy || atImageCap}
            onClick={() => setRegenOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" />
            Regenerate photo
          </button>
        </Tip>

        {!editingHeadline ? (
          <button
            type="button"
            data-testid="draft-edit-headline-btn"
            disabled={busy}
            onClick={() => {
              setHeadlineDraft(draftHeadlineFromCaption(item.meta?.caption))
              setEditingHeadline(true)
            }}
            className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-ac hover:text-ac disabled:opacity-50"
          >
            <Pencil className="h-4 w-4" strokeWidth={2.5} />
            Edit headline
          </button>
        ) : (
          <div className="flex w-full flex-wrap items-center gap-2">
            <input
              data-testid="headline-editor"
              value={headlineDraft}
              onChange={(e) => setHeadlineDraft(e.target.value)}
              className="min-w-[12rem] flex-1 rounded-full border border-bd bg-bg px-3 py-1.5 text-sm"
              aria-label="Headline"
            />
            <button
              type="button"
              data-testid="headline-save-btn"
              disabled={busy}
              onClick={saveHeadline}
              className="rounded-full bg-ac px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-50"
            >
              Recompose
            </button>
            <button
              type="button"
              data-testid="headline-cancel-btn"
              disabled={busy}
              onClick={() => setEditingHeadline(false)}
              className="rounded-full border border-bd px-3 py-1.5 text-sm font-semibold"
            >
              Cancel
            </button>
          </div>
        )}

        <button
          type="button"
          data-testid="draft-reject-btn"
          disabled={busy}
          onClick={() => {
            setRejectErr('')
            setRejectOpen(true)
          }}
          className="inline-flex items-center gap-1.5 rounded-full border border-bd px-3 py-1.5 text-sm font-semibold hover:border-red hover:text-red disabled:opacity-50"
        >
          <PressIcon icon={RotateCcw} className="h-4 w-4" />
          Reject
        </button>
      </div>

      {regenOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="regen-dialog-title"
          data-testid="regenerate-dialog"
        >
          <div className="w-full max-w-md rounded-2xl border border-bd bg-bg p-4 shadow-xl">
            <div className="flex items-center justify-between gap-2">
              <h4 id="regen-dialog-title" className="font-display text-lg font-semibold">
                Regenerate photo
              </h4>
              <button type="button" aria-label="Close" onClick={() => setRegenOpen(false)}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="mt-2 text-sm text-tx2">Add a corrective note for the image job.</p>
            <textarea
              data-testid="regenerate-note"
              value={regenNote}
              onChange={(e) => setRegenNote(e.target.value)}
              rows={4}
              className="mt-3 w-full rounded-xl border border-bd bg-bg2/50 px-3 py-2 text-sm"
              placeholder="What should change in the photo?"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-full border border-bd px-4 py-2 text-sm font-semibold"
                onClick={() => setRegenOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="regenerate-submit"
                disabled={!regenNote.trim() || busy}
                onClick={submitRegenerate}
                className="rounded-full bg-ac px-4 py-2 text-sm font-semibold text-bg disabled:opacity-50"
              >
                Queue regenerate
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {rejectOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reject-dialog-title"
          data-testid="reject-dialog"
        >
          <div className="w-full max-w-md rounded-2xl border border-bd bg-bg p-4 shadow-xl">
            <div className="flex items-center justify-between gap-2">
              <h4 id="reject-dialog-title" className="font-display text-lg font-semibold">
                Reject draft
              </h4>
              <button type="button" aria-label="Close" onClick={() => setRejectOpen(false)}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <textarea
              data-testid="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
              className="mt-3 w-full rounded-xl border border-bd bg-bg2/50 px-3 py-2 text-sm"
              placeholder="Why are you sending this back?"
            />
            {rejectErr ? (
              <p className="mt-2 text-sm text-red" data-testid="reject-reason-error">
                {rejectErr}
              </p>
            ) : null}
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-full border border-bd px-4 py-2 text-sm font-semibold"
                onClick={() => setRejectOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="reject-submit"
                disabled={busy}
                onClick={submitReject}
                className="rounded-full border border-red px-4 py-2 text-sm font-semibold text-red disabled:opacity-50"
              >
                Send back
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {atImageCap ? (
        <p className="mt-2 text-xs text-tx3" data-testid="regenerate-cap-hint">
          <Sparkles className="mr-1 inline h-3 w-3" aria-hidden />
          Regenerate is disabled at the daily image cap.
        </p>
      ) : null}
    </section>
  )
}
