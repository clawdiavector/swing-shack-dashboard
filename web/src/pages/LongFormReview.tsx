import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ExternalLink,
  FileText,
  Loader2,
  MessageCircle,
  Pencil,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { BrandChip } from '../components/BrandChip'
import { useBrandScope } from '../components/BrandSwitch'
import { useBrand } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { brandDisplayName } from '../lib/planning'

type ReviewQueueItem = {
  draft_id: string
  brand_id: string
  brief_id: string
  content_type: string
  writer_mode: string
  title: string
  status: string
  reviewer_id?: string | null
  current_revision?: number
  last_updated_at?: string
  warnings?: string[]
  metrics?: {
    sections_total: number
    unapproved_sections: number
    rejected_sections: number
    pending_rewrites: number
    blocking_comments: number
    evidence_needed: number
  }
}

type FactCheckRow = {
  claim: string
  article_sentence?: string
  evidence_layer?: string
  evidence_source?: string
  evidence_type?: string
  status: string
  action_taken?: string
}

type ReviewSection = {
  section_id: string
  level: number
  heading: string
  current_body: string
  original_body: string
  approved: boolean
  rejected: boolean
  rewrite_pending: boolean
  last_action?: string | null
  last_action_at?: string | null
  last_actor?: string | null
}

type ReviewComment = {
  comment_id: string
  body: string
  actor: string
  at: string
  blocking?: boolean
  resolved?: boolean
  section_id?: string | null
  claim_id?: string | null
}

type ReviewRevision = {
  revision: number
  action: string
  actor: string
  at: string
  section_id?: string | null
  before_excerpt?: string | null
  after_excerpt?: string | null
  reason?: string | null
  claim_id?: string | null
}

type ReviewRecord = {
  schema_version: number
  review_version: string
  brand_id: string
  brief_id: string
  content_type: string
  writer_mode: string
  status: string
  reviewer_id?: string | null
  current_revision: number
  sections: ReviewSection[]
  comments: ReviewComment[]
  revisions: ReviewRevision[]
  approved_for_publishing_at?: string | null
  approved_by?: string | null
}

type ReviewDetail = {
  ok: boolean
  summary?: ReviewQueueItem
  record?: ReviewRecord
  fact_check_rows?: FactCheckRow[]
  brand_knowledge_excerpt?: Record<string, unknown>
  writer_artifact_path?: string
  writer_artifact_content_hash?: string
  error?: string
}

type ApprovalBlockers = {
  ok: boolean
  blockers?: {
    blocking: boolean
    evidence_needed_count: number
    pending_rewrites: number
    rejected_sections: number
    blocking_comments: number
    unapproved_sections: number
    blocking_comments_list: string[]
    evidence_needed_rows: number
  }
  error?: string
}

type Article = {
  ok: boolean
  title?: string
  body?: string
  body_markdown?: string
  cta?: string
  cta_url?: string
  source?: 'review' | 'writer'
  error?: string
}

const STATUS_TONE: Record<string, 'green' | 'gold' | 'mute' | 'red'> = {
  DRAFT_FOR_REVIEW: 'gold',
  IN_REVIEW: 'gold',
  CHANGES_REQUESTED: 'red',
  READY_FOR_APPROVAL: 'green',
  APPROVED_FOR_PUBLISHING: 'green',
  REJECTED: 'red',
}

type PillTone = 'gold' | 'green' | 'red' | 'ghost'

const PILL_CLS: Record<PillTone, string> = {
  gold: 'bg-yel text-bg hover:bg-yel/90',
  green: 'bg-ac text-bg hover:bg-ac/90',
  red: 'bg-red text-bg hover:bg-red/90',
  ghost: 'glass-pill border border-white/10 text-tx hover:border-ac hover:text-ac',
}

function PillButton({
  icon: Icon,
  tone = 'ghost',
  disabled,
  onClick,
  children,
  tip,
}: {
  icon?: typeof Check
  tone?: PillTone
  disabled?: boolean
  onClick?: () => void
  children: React.ReactNode
  tip?: string
}) {
  const inner = (
    <>
      {Icon ? <Icon className="h-4 w-4" strokeWidth={2.5} /> : null}
      {children}
    </>
  )
  const cls = `inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition-colors duration-150 ${PILL_CLS[tone]}`
  const button = (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`${cls} ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      {inner}
    </button>
  )
  return tip ? <span title={tip}>{button}</span> : button
}

function statusLabel(status: string): string {
  return status.replace(/_/g, ' ')
}

const BADGE_TONE_CLS: Record<'green' | 'gold' | 'red' | 'mute', string> = {
  green: 'bg-ac/15 text-ac',
  gold: 'bg-yel/15 text-yel',
  red: 'bg-red/15 text-red',
  mute: 'glass-pill text-tx2',
}

function PillBadge({
  tone = 'mute',
  children,
}: {
  tone?: 'mute' | 'gold' | 'green' | 'red'
  children: React.ReactNode
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold tracking-wide uppercase ${BADGE_TONE_CLS[tone]}`}
    >
      {children}
    </span>
  )
}

function evidenceLayerShort(layer?: string): string {
  if (!layer) return '—'
  return layer.replace(/_/g, ' ').toLowerCase()
}

export function LongFormReview() {
  const { brandId: focusedBrandId } = useBrand()
  useBrandScope() // ensures the brand switch is mounted (used by BrandChip below)
  const brand = (focusedBrandId && focusedBrandId !== 'all') ? focusedBrandId : 'stick'
  const [queue, setQueue] = useState<ReviewQueueItem[]>([])
  const [selectedDraft, setSelectedDraft] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [article, setArticle] = useState<Article | null>(null)
  const [blockers, setBlockers] = useState<ApprovalBlockers | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [highlightClaimId, setHighlightClaimId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'article' | 'context' | 'fact-check' | 'history' | 'comments'>(
    'article',
  )

  function loadQueue() {
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const r = await fetch(`/api/review/v1/queue/${brand}`, { credentials: 'include' })
        if (!r.ok) throw new Error(`queue HTTP ${r.status}`)
        const data = await r.json()
        if (!data.ok) throw new Error(data.error || 'queue not ok')
        setQueue(data.queue || [])
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setLoading(false)
      }
    }
    void run()
  }

  useEffect(() => {
    loadQueue()
  }, [brand])

  useEffect(() => {
    if (!selectedDraft) {
      setDetail(null)
      setArticle(null)
      setBlockers(null)
      return
    }
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const [r1, r2, r3] = await Promise.all([
          fetch(`/api/review/v1/${brand}/${selectedDraft}`, { credentials: 'include' }),
          fetch(`/api/review/v1/${brand}/${selectedDraft}/article`, { credentials: 'include' }),
          fetch(`/api/review/v1/${brand}/${selectedDraft}/blockers`, { credentials: 'include' }),
        ])
        const d1 = await r1.json()
        const d2 = await r2.json()
        const d3 = await r3.json()
        setDetail(d1)
        setArticle(d2)
        setBlockers(d3)
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setLoading(false)
      }
    }
    void run()
  }, [brand, selectedDraft])

  async function callAction(path: string, body: Record<string, unknown>, label: string) {
    setBusy(label)
    try {
      const r = await fetch(path, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await r.json()
      if (!r.ok || !data.ok) {
        setError(data.error || `HTTP ${r.status}`)
        return
      }
      // reload queue + detail
      loadQueue()
      if (selectedDraft) {
        const [r1, r2, r3] = await Promise.all([
          fetch(`/api/review/v1/${brand}/${selectedDraft}`, { credentials: 'include' }),
          fetch(`/api/review/v1/${brand}/${selectedDraft}/article`, { credentials: 'include' }),
          fetch(`/api/review/v1/${brand}/${selectedDraft}/blockers`, { credentials: 'include' }),
        ])
        setDetail(await r1.json())
        setArticle(await r2.json())
        setBlockers(await r3.json())
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro
        here="/review"
        title={
          <span>
            Long-form Review{' '}
            <span className="text-tx3 font-normal">— drafts from the campaign-os-writer pipeline</span>
          </span>
        }
        actions={
          <PillButton icon={Sparkles} tone="ghost" onClick={() => (window.location.href = '/review')}>
            Creative Review
          </PillButton>
        }
      >
        The human gate between the frozen Writer V1 and (future) publishing. Reviewers
        approve / edit / rewrite sections, check claims, leave notes. Nothing leaves this
        page without an explicit human action.
      </PageIntro>

      <div className="flex flex-wrap items-center gap-2">
        <Link
          to="/review"
          className="inline-flex items-center gap-1 text-xs uppercase tracking-wide text-tx3 hover:text-tx"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> back to Creative Review
        </Link>
        <BrandChip brandId={brand} />
      </div>

      {error ? (
        <div className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">
          {error}
        </div>
      ) : null}

      {loading && !detail ? (
        <div className="glass flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm text-tx3">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading {brandDisplayName(brand)} long-form queue…
        </div>
      ) : null}

      {!selectedDraft ? (
        <QueueView queue={queue} onPick={setSelectedDraft} brand={brand} />
      ) : (
        <DetailView
          brand={brand}
          draftId={selectedDraft}
          detail={detail}
          article={article}
          blockers={blockers}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          highlightClaimId={highlightClaimId}
          setHighlightClaimId={setHighlightClaimId}
          onBack={() => {
            setSelectedDraft(null)
            setActiveTab('article')
            setHighlightClaimId(null)
          }}
          callAction={callAction}
          busy={busy}
        />
      )}
    </div>
  )
}

function QueueView({
  queue,
  onPick,
  brand,
}: {
  queue: ReviewQueueItem[]
  onPick: (id: string) => void
  brand: string
}) {
  if (queue.length === 0) {
    return (
      <div className="glass rounded-2xl border border-white/10 p-6 text-sm text-tx3">
        <p className="font-semibold text-tx">No long-form drafts in the {brandDisplayName(brand)} queue.</p>
        <p className="mt-2 text-tx3">
          The Writer is operator-triggered (on-demand, not a cronjob). When a Writer
          artifact is ingested from the heidi outbox or the in-repo baked directory, it
          appears here.
        </p>
      </div>
    )
  }
  return (
    <div className="space-y-3">
      {queue.map((item) => (
        <button
          type="button"
          key={item.draft_id}
          onClick={() => onPick(item.draft_id)}
          className="glass block w-full rounded-2xl border border-white/10 p-4 text-left transition-colors hover:border-yel/40"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="font-display text-base font-semibold leading-snug text-tx">
                {item.title}
              </p>
              <p className="mt-1 text-xs text-tx3">
                brief <span className="font-mono text-tx2">{item.brief_id}</span> · mode{' '}
                <span className="font-mono text-tx2">{item.writer_mode}</span> · type{' '}
                <span className="font-mono text-tx2">{item.content_type}</span>
              </p>
              {(item.warnings || []).length > 0 ? (
                <ul className="mt-2 space-y-0.5 text-xs text-yel">
                  {(item.warnings || []).map((w, idx) => (
                    <li key={idx}>• {w}</li>
                  ))}
                </ul>
              ) : null}
            </div>
            <div className="flex flex-col items-end gap-2">
              <PillBadge tone={STATUS_TONE[item.status] || 'mute'}>{statusLabel(item.status)}</PillBadge>
              {item.metrics ? (
                <p className="text-[10px] uppercase tracking-wide text-tx3">
                  {item.metrics.unapproved_sections}/{item.metrics.sections_total} sections open
                </p>
              ) : null}
              <ChevronRight className="h-4 w-4 text-tx3" />
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}

function DetailView(props: {
  brand: string
  draftId: string
  detail: ReviewDetail | null
  article: Article | null
  blockers: ApprovalBlockers | null
  activeTab: 'article' | 'context' | 'fact-check' | 'history' | 'comments'
  setActiveTab: (t: 'article' | 'context' | 'fact-check' | 'history' | 'comments') => void
  highlightClaimId: number | null
  setHighlightClaimId: (n: number | null) => void
  onBack: () => void
  callAction: (
    path: string,
    body: Record<string, unknown>,
    label: string,
  ) => Promise<void>
  busy: string | null
}) {
  const {
    brand,
    draftId,
    detail,
    article,
    blockers,
    activeTab,
    setActiveTab,
    highlightClaimId,
    setHighlightClaimId,
    onBack,
    callAction,
    busy,
  } = props

  const record = detail?.record
  const summary = detail?.summary
  const factRows = detail?.fact_check_rows || []
  const sections = record?.sections || []
  const comments = record?.comments || []
  const revisions = record?.revisions || []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1 text-xs uppercase tracking-wide text-tx3 hover:text-tx"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> back to queue
        </button>
        {summary ? (
          <PillBadge tone={STATUS_TONE[summary.status] || 'mute'}>{statusLabel(summary.status)}</PillBadge>
        ) : null}
        <p className="font-display text-lg font-semibold leading-snug text-tx">
          {summary?.title || draftId}
        </p>
      </div>

      {detail && detail.ok === false ? (
        <div className="rounded-2xl border border-red/40 bg-red/10 px-4 py-3 text-sm text-red">
          {detail.error || 'Review not found.'}
        </div>
      ) : null}

      {/* Tabs */}
      <div className="glass-pill inline-flex items-center gap-1 rounded-full border border-white/10 p-1">
        {(['article', 'context', 'fact-check', 'history', 'comments'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setActiveTab(t)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${
              activeTab === t ? 'bg-yel/15 text-yel' : 'text-tx3 hover:text-tx'
            }`}
          >
            {t === 'article' && <FileText className="h-3.5 w-3.5" />}
            {t === 'context' && <Sparkles className="h-3.5 w-3.5" />}
            {t === 'fact-check' && <ClipboardCheck className="h-3.5 w-3.5" />}
            {t === 'history' && <RefreshCw className="h-3.5 w-3.5" />}
            {t === 'comments' && <MessageCircle className="h-3.5 w-3.5" />}
            {t === 'article'
              ? 'Article'
              : t === 'context'
                ? 'Context'
                : t === 'fact-check'
                  ? `Fact-check (${factRows.length})`
                  : t === 'history'
                    ? `History (${revisions.length})`
                    : `Comments (${comments.filter((c) => !c.resolved).length})`}
          </button>
        ))}
      </div>

      {activeTab === 'article' ? (
        <ArticleTab
          article={article}
          sections={sections}
          highlightClaimId={highlightClaimId}
          blockers={blockers}
          brand={brand}
          draftId={draftId}
          callAction={callAction}
          busy={busy}
        />
      ) : null}
      {activeTab === 'context' ? <ContextTab detail={detail} blockers={blockers} /> : null}
      {activeTab === 'fact-check' ? (
        <FactCheckTab
          factRows={factRows}
          highlightClaimId={highlightClaimId}
          setHighlightClaimId={setHighlightClaimId}
        />
      ) : null}
      {activeTab === 'history' ? <HistoryTab revisions={revisions} /> : null}
      {activeTab === 'comments' ? (
        <CommentsTab
          brand={brand}
          draftId={draftId}
          comments={comments}
          sections={sections}
          callAction={callAction}
          busy={busy}
        />
      ) : null}
    </div>
  )
}

function ArticleTab({
  article,
  sections,
  highlightClaimId,
  blockers,
  brand,
  draftId,
  callAction,
  busy,
}: {
  article: Article | null
  sections: ReviewSection[]
  highlightClaimId: number | null
  blockers: ApprovalBlockers | null
  brand: string
  draftId: string
  callAction: (
    path: string,
    body: Record<string, unknown>,
    label: string,
  ) => Promise<void>
  busy: string | null
}) {
  const canApprove = blockers && blockers.blockers ? !blockers.blockers.blocking : false
  const blocking = blockers?.blockers?.blocking

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <article className="glass rounded-2xl border border-white/10 p-6">
        {article?.title ? (
          <h1 className="font-display text-3xl font-semibold leading-tight text-tx">
            {article.title}
          </h1>
        ) : (
          <h1 className="font-display text-3xl font-semibold leading-tight text-tx">
            Article body
          </h1>
        )}
        <p className="mt-1 text-xs uppercase tracking-wide text-tx3">
          customer-facing article · built from the writer artifact
        </p>
        <div className="prose prose-invert mt-6 max-w-none text-base leading-relaxed text-tx">
          {(article?.body_markdown || article?.body || '')
            .split('\n')
            .map((line, i) => (
              <p
                key={i}
                id={`p-${i}`}
                className={
                  highlightClaimId !== null && highlightClaimId === i
                    ? 'rounded-md bg-yel/10 px-2 py-1 ring-2 ring-yel/40'
                    : ''
                }
              >
                {line || '\u00A0'}
              </p>
            ))}
        </div>
        {article?.cta ? (
          <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-yel/40 bg-yel/10 px-4 py-2 text-sm font-semibold text-yel">
            <a
              href={article.cta_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2"
            >
              {article.cta} <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </p>
        ) : null}
      </article>

      <aside className="space-y-3">
        {/* Approval summary */}
        <section className="glass rounded-2xl border border-white/10 p-4">
          <p className="text-xs uppercase tracking-wide text-tx3">Approval status</p>
          {blocking ? (
            <p className="mt-2 inline-flex items-center gap-2 rounded-full border border-red/40 bg-red/10 px-3 py-1 text-xs font-semibold text-red">
              <AlertTriangle className="h-3.5 w-3.5" /> blocked
            </p>
          ) : (
            <p className="mt-2 inline-flex items-center gap-2 rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300">
              <Check className="h-3.5 w-3.5" /> ready
            </p>
          )}
          {blockers?.blockers ? (
            <ul className="mt-3 space-y-1 text-xs text-tx3">
              <li>
                unapproved sections:{' '}
                <span className="font-mono text-tx2">{blockers.blockers.unapproved_sections}</span>
              </li>
              <li>
                rejected sections:{' '}
                <span className="font-mono text-tx2">{blockers.blockers.rejected_sections}</span>
              </li>
              <li>
                pending rewrites:{' '}
                <span className="font-mono text-tx2">{blockers.blockers.pending_rewrites}</span>
              </li>
              <li>
                blocking comments:{' '}
                <span className="font-mono text-tx2">{blockers.blockers.blocking_comments}</span>
              </li>
              <li>
                evidence-need rows:{' '}
                <span className="font-mono text-tx2">{blockers.blockers.evidence_needed_count}</span>
              </li>
            </ul>
          ) : null}
          <div className="mt-3 flex flex-col gap-2">
            <PillButton
              icon={Check}
              tone="green"
              disabled={!canApprove || busy === 'approve'}
              onClick={() =>
                void callAction(
                  `/api/review/v1/${brand}/${draftId}/approve`,
                  {},
                  'approve',
                )
              }
            >
              {busy === 'approve' ? 'Approving…' : 'Approve for publishing'}
            </PillButton>
            <PillButton
              icon={X}
              tone="ghost"
              disabled={busy === 'reject'}
              onClick={() => {
                const reason = window.prompt('Reason for rejection (required):')
                if (!reason) return
                void callAction(
                  `/api/review/v1/${brand}/${draftId}/reject`,
                  { reason, explanation: '' },
                  'reject',
                )
              }}
            >
              Reject draft
            </PillButton>
          </div>
          {!canApprove && blocking ? (
            <p className="mt-2 text-[11px] text-red">
              Resolve the blockers above before approval is allowed.
            </p>
          ) : null}
        </section>

        {/* Sections */}
        <section className="glass rounded-2xl border border-white/10 p-4">
          <p className="text-xs uppercase tracking-wide text-tx3">
            Sections ({sections.length})
          </p>
          <ul className="mt-2 space-y-1">
            {sections.map((s) => (
              <li
                key={s.section_id}
                className="flex items-center gap-2 rounded-md border border-white/5 bg-bg/40 px-2 py-1.5 text-xs"
              >
                <span
                  className={`grid h-5 w-5 place-items-center rounded-full ${
                    s.approved
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : s.rejected
                        ? 'bg-red/15 text-red'
                        : s.rewrite_pending
                          ? 'bg-yel/15 text-yel'
                          : 'bg-tx3/15 text-tx3'
                  }`}
                  title={
                    s.approved
                      ? 'approved'
                      : s.rejected
                        ? 'rejected'
                        : s.rewrite_pending
                          ? 'rewrite pending'
                          : 'unapproved'
                  }
                >
                  {s.approved ? (
                    <Check className="h-3 w-3" />
                  ) : s.rejected ? (
                    <X className="h-3 w-3" />
                  ) : s.rewrite_pending ? (
                    <RefreshCw className="h-3 w-3" />
                  ) : (
                    '·'
                  )}
                </span>
                <span className="truncate text-tx2">{s.heading}</span>
              </li>
            ))}
          </ul>
        </section>
      </aside>

      {/* Section detail — full width below the article */}
      <div className="space-y-4 lg:col-span-2">
        {sections.map((s) => (
          <SectionBlock
            key={s.section_id}
            section={s}
            brand={brand}
            draftId={draftId}
            callAction={callAction}
            busy={busy}
          />
        ))}
      </div>
    </div>
  )
}

function SectionBlock({
  section,
  brand,
  draftId,
  callAction,
  busy,
}: {
  section: ReviewSection
  brand: string
  draftId: string
  callAction: (
    path: string,
    body: Record<string, unknown>,
    label: string,
  ) => Promise<void>
  busy: string | null
}) {
  const [editing, setEditing] = useState(false)
  const [editBody, setEditBody] = useState(section.current_body)
  const [editReason, setEditReason] = useState('')
  const [rewriteInstr, setRewriteInstr] = useState('')
  const [showRewrite, setShowRewrite] = useState(false)

  return (
    <div className="glass rounded-2xl border border-white/10 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-display text-base font-semibold text-tx">{section.heading}</p>
        {section.approved ? <PillBadge tone="green">approved</PillBadge> : null}
        {section.rejected ? <PillBadge tone="red">rejected</PillBadge> : null}
        {section.rewrite_pending ? <PillBadge tone="gold">rewrite pending</PillBadge> : null}
      </div>

      {editing ? (
        <div className="mt-3 space-y-2">
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            className="w-full rounded-md border border-white/10 bg-bg/40 px-3 py-2 text-sm text-tx"
            rows={6}
          />
          <input
            type="text"
            placeholder="Reason (optional)"
            value={editReason}
            onChange={(e) => setEditReason(e.target.value)}
            className="w-full rounded-md border border-white/10 bg-bg/40 px-3 py-2 text-xs text-tx"
          />
          <div className="flex gap-2">
            <PillButton
              icon={Check}
              tone="green"
              disabled={busy === `edit:${section.section_id}`}
              onClick={() => {
                void callAction(
                  `/api/review/v1/${brand}/${draftId}/sections/${section.section_id}/edit`,
                  { body: editBody, reason: editReason },
                  `edit:${section.section_id}`,
                ).then(() => setEditing(false))
              }}
            >
              Save edit
            </PillButton>
            <PillButton icon={X} tone="ghost" onClick={() => setEditing(false)}>
              Cancel
            </PillButton>
          </div>
        </div>
      ) : (
        <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-tx">
          {section.current_body}
        </div>
      )}

      {showRewrite ? (
        <div className="mt-3 space-y-2">
          <textarea
            placeholder="Rewrite instruction (pass to frozen Writer V1)"
            value={rewriteInstr}
            onChange={(e) => setRewriteInstr(e.target.value)}
            className="w-full rounded-md border border-white/10 bg-bg/40 px-3 py-2 text-sm text-tx"
            rows={3}
          />
          <div className="flex gap-2">
            <PillButton
              icon={RefreshCw}
              tone="ghost"
              disabled={busy === `rewrite:${section.section_id}` || !rewriteInstr.trim()}
              onClick={() => {
                void callAction(
                  `/api/review/v1/${brand}/${draftId}/sections/${section.section_id}/request-rewrite`,
                  { instruction: rewriteInstr },
                  `rewrite:${section.section_id}`,
                ).then(() => setShowRewrite(false))
              }}
            >
              Request rewrite
            </PillButton>
            <PillButton icon={X} tone="ghost" onClick={() => setShowRewrite(false)}>
              Cancel
            </PillButton>
          </div>
        </div>
      ) : null}

      {!editing && !showRewrite ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <PillButton
            icon={Check}
            tone="ghost"
            disabled={busy === `approve:${section.section_id}` || section.approved}
            onClick={() =>
              void callAction(
                `/api/review/v1/${brand}/${draftId}/sections/${section.section_id}/approve`,
                {},
                `approve:${section.section_id}`,
              )
            }
          >
            Approve section
          </PillButton>
          <PillButton
            icon={Pencil}
            tone="ghost"
            onClick={() => {
              setEditBody(section.current_body)
              setEditing(true)
            }}
          >
            Edit
          </PillButton>
          <PillButton icon={RefreshCw} tone="ghost" onClick={() => setShowRewrite(true)}>
            Request rewrite
          </PillButton>
          <PillButton
            icon={X}
            tone="ghost"
            disabled={busy === `reject:${section.section_id}` || section.rejected}
            onClick={() => {
              const reason = window.prompt('Reason for rejection:')
              if (!reason) return
              void callAction(
                `/api/review/v1/${brand}/${draftId}/sections/${section.section_id}/reject`,
                { reason },
                `reject:${section.section_id}`,
              )
            }}
          >
            Reject section
          </PillButton>
        </div>
      ) : null}

      {section.last_action_at ? (
        <p className="mt-3 text-[11px] text-tx3">
          last action: {section.last_action} by {section.last_actor} at{' '}
          {new Date(section.last_action_at).toLocaleString()}
        </p>
      ) : null}
    </div>
  )
}

function ContextTab({
  detail,
  blockers,
}: {
  detail: ReviewDetail | null
  blockers: ApprovalBlockers | null
}) {
  const excerpt = detail?.brand_knowledge_excerpt || {}
  const writerPath = detail?.writer_artifact_path
  const writerHash = detail?.writer_artifact_content_hash

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="glass rounded-2xl border border-white/10 p-4">
        <p className="text-xs uppercase tracking-wide text-tx3">Writer artifact</p>
        <p className="mt-2 break-all font-mono text-xs text-tx2">{writerPath}</p>
        <p className="mt-1 font-mono text-xs text-tx3">content_hash: {writerHash}</p>
        <p className="mt-3 text-xs text-tx3">
          Immutable Writer output. The Review layer never mutates the artifact; it only
          records human actions in its own store.
        </p>
      </section>
      <section className="glass rounded-2xl border border-white/10 p-4">
        <p className="text-xs uppercase tracking-wide text-tx3">Approval gate</p>
        <ul className="mt-3 space-y-1 text-xs text-tx3">
          <li>
            blocking:{' '}
            <span
              className={`font-mono ${blockers?.blockers?.blocking ? 'text-red' : 'text-emerald-300'}`}
            >
              {String(blockers?.blockers?.blocking ?? '—')}
            </span>
          </li>
          <li>
            evidence-need rows:{' '}
            <span className="font-mono text-tx2">
              {blockers?.blockers?.evidence_needed_rows ?? '—'}
            </span>
          </li>
          <li>
            pending rewrites:{' '}
            <span className="font-mono text-tx2">{blockers?.blockers?.pending_rewrites ?? '—'}</span>
          </li>
          <li>
            rejected sections:{' '}
            <span className="font-mono text-tx2">{blockers?.blockers?.rejected_sections ?? '—'}</span>
          </li>
          <li>
            blocking comments:{' '}
            <span className="font-mono text-tx2">{blockers?.blockers?.blocking_comments ?? '—'}</span>
          </li>
          <li>
            unapproved sections:{' '}
            <span className="font-mono text-tx2">{blockers?.blockers?.unapproved_sections ?? '—'}</span>
          </li>
        </ul>
      </section>
      <section className="glass rounded-2xl border border-white/10 p-4 lg:col-span-2">
        <p className="text-xs uppercase tracking-wide text-tx3">Brand knowledge excerpt</p>
        <ul className="mt-3 space-y-2 text-xs text-tx3">
          {Object.entries(excerpt).map(([k, v]) => (
            <li key={k}>
              <span className="font-semibold text-tx2">{k}:</span>{' '}
              <span className="text-tx3">
                {Array.isArray(v) ? v.join(', ') : String(v ?? '')}
              </span>
            </li>
          ))}
          {Object.keys(excerpt).length === 0 ? (
            <li className="text-tx3">No brand knowledge loaded.</li>
          ) : null}
        </ul>
      </section>
    </div>
  )
}

function FactCheckTab({
  factRows,
  highlightClaimId,
  setHighlightClaimId,
}: {
  factRows: FactCheckRow[]
  highlightClaimId: number | null
  setHighlightClaimId: (n: number | null) => void
}) {
  const grouped = useMemo(() => {
    const by: Record<string, FactCheckRow[]> = {}
    for (const r of factRows) {
      const k = r.status || 'UNCLASSIFIED'
      if (!by[k]) by[k] = []
      by[k].push(r)
    }
    return by
  }, [factRows])

  return (
    <div className="space-y-4">
      <p className="text-xs text-tx3">
        Each claim is verified against the frozen evidence hierarchy. Click a row to
        navigate to the article sentence it claims.
      </p>
      {Object.entries(grouped).map(([status, rows]) => (
        <section key={status} className="glass rounded-2xl border border-white/10 p-4">
          <div className="flex items-center gap-2">
            <p className="text-xs uppercase tracking-wide text-tx3">{status}</p>
            <PillBadge
              tone={
                status === 'VERIFIED'
                  ? 'green'
                  : status === 'EVIDENCE NEEDED'
                    ? 'red'
                    : status === 'QUALIFIED'
                      ? 'gold'
                      : 'mute'
              }
            >
              {rows.length}
            </PillBadge>
          </div>
          <ul className="mt-3 space-y-2">
            {rows.map((r) => {
              const idx = factRows.indexOf(r)
              return (
                <li
                  key={idx}
                  className={`rounded-md border ${
                    highlightClaimId === idx ? 'border-yel/50 bg-yel/10' : 'border-white/5 bg-bg/40'
                  } px-3 py-2 text-xs`}
                >
                  <button
                    type="button"
                    onClick={() => setHighlightClaimId(idx)}
                    className="w-full text-left"
                  >
                    <p className="font-semibold text-tx">{r.claim}</p>
                    <p className="mt-0.5 text-tx3">
                      {r.article_sentence ? (
                        <span className="line-clamp-2 italic">"{r.article_sentence}"</span>
                      ) : null}
                    </p>
                    <p className="mt-1 text-[11px] text-tx3">
                      layer: <span className="text-tx2">{evidenceLayerShort(r.evidence_layer)}</span> ·
                      source: <span className="text-tx2">{r.evidence_source || '—'}</span>
                    </p>
                    {r.action_taken ? (
                      <p className="mt-1 text-[11px] text-tx3">action: {r.action_taken}</p>
                    ) : null}
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
      {factRows.length === 0 ? (
        <p className="text-xs text-tx3">No fact-check rows in the writer artifact.</p>
      ) : null}
    </div>
  )
}

function HistoryTab({ revisions }: { revisions: ReviewRevision[] }) {
  return (
    <section className="glass rounded-2xl border border-white/10 p-4">
      <p className="text-xs uppercase tracking-wide text-tx3">Revision history</p>
      <ol className="mt-3 space-y-3 text-xs">
        {revisions.length === 0 ? (
          <li className="text-tx3">No revisions yet.</li>
        ) : (
          revisions.map((r) => (
            <li
              key={r.revision}
              className="rounded-md border border-white/5 bg-bg/40 px-3 py-2"
            >
              <p className="font-semibold text-tx2">
                #{r.revision} · {r.action}
              </p>
              <p className="mt-0.5 text-tx3">
                {r.actor} · {new Date(r.at).toLocaleString()}
                {r.section_id ? <> · section <span className="font-mono">{r.section_id}</span></> : null}
              </p>
              {r.reason ? <p className="mt-1 text-tx3">{r.reason}</p> : null}
            </li>
          ))
        )}
      </ol>
    </section>
  )
}

function CommentsTab({
  brand,
  draftId,
  comments,
  sections,
  callAction,
  busy,
}: {
  brand: string
  draftId: string
  comments: ReviewComment[]
  sections: ReviewSection[]
  callAction: (
    path: string,
    body: Record<string, unknown>,
    label: string,
  ) => Promise<void>
  busy: string | null
}) {
  const [body, setBody] = useState('')
  const [blocking, setBlocking] = useState(false)
  const [sectionId, setSectionId] = useState<string>('')

  return (
    <section className="glass rounded-2xl border border-white/10 p-4">
      <p className="text-xs uppercase tracking-wide text-tx3">Add comment</p>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Leave a note for the writer / future reviewers"
        rows={3}
        className="mt-2 w-full rounded-md border border-white/10 bg-bg/40 px-3 py-2 text-xs text-tx"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <label className="inline-flex items-center gap-1 text-tx3">
          <input
            type="checkbox"
            checked={blocking}
            onChange={(e) => setBlocking(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          blocking (blocks approval until resolved)
        </label>
        <select
          value={sectionId}
          onChange={(e) => setSectionId(e.target.value)}
          className="rounded-md border border-white/10 bg-bg/40 px-2 py-1 text-xs text-tx"
        >
          <option value="">(no specific section)</option>
          {sections.map((s) => (
            <option key={s.section_id} value={s.section_id}>
              {s.heading}
            </option>
          ))}
        </select>
        <PillButton
          icon={MessageCircle}
          tone="ghost"
          disabled={!body.trim() || busy === 'comment'}
          onClick={() => {
            void callAction(
              `/api/review/v1/${brand}/${draftId}/comments`,
              { body, blocking, section_id: sectionId || null, claim_id: null },
              'comment',
            ).then(() => {
              setBody('')
              setBlocking(false)
              setSectionId('')
            })
          }}
        >
          Add comment
        </PillButton>
      </div>

      <p className="mt-6 text-xs uppercase tracking-wide text-tx3">Existing comments</p>
      <ul className="mt-2 space-y-2">
        {comments.length === 0 ? (
          <li className="text-xs text-tx3">No comments yet.</li>
        ) : (
          comments.map((c) => (
            <li
              key={c.comment_id}
              className={`rounded-md border ${
                c.resolved
                  ? 'border-emerald-500/30 bg-emerald-500/5'
                  : c.blocking
                    ? 'border-red/40 bg-red/5'
                    : 'border-white/5 bg-bg/40'
              } px-3 py-2 text-xs`}
            >
              <p className="text-tx2">{c.body}</p>
              <p className="mt-1 text-[11px] text-tx3">
                {c.actor} · {new Date(c.at).toLocaleString()}
                {c.section_id ? (
                  <>
                    {' · section '}
                    <span className="font-mono">{c.section_id}</span>
                  </>
                ) : null}
                {c.blocking ? <span className="ml-1 text-red">[blocking]</span> : null}
                {c.resolved ? <span className="ml-1 text-emerald-300">[resolved]</span> : null}
              </p>
              {!c.resolved ? (
                <div className="mt-2">
                  <PillButton
                    icon={Check}
                    tone="ghost"
                    disabled={busy === `resolve:${c.comment_id}`}
                    onClick={() =>
                      void callAction(
                        `/api/review/v1/${brand}/${draftId}/comments/${c.comment_id}/resolve`,
                        {},
                        `resolve:${c.comment_id}`,
                      )
                    }
                  >
                    Resolve
                  </PillButton>
                </div>
              ) : null}
            </li>
          ))
        )}
      </ul>
    </section>
  )
}