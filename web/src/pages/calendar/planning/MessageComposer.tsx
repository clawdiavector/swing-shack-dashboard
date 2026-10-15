import { useMemo, useState } from 'react'
import { copyText } from '../../../lib/planMessages'

type Field = { key: string; label: string; placeholder: string; remember?: boolean }

const STORE = 'cos_msg_'

function recall(f: Field): string {
  if (!f.remember) return ''
  try {
    return window.localStorage.getItem(STORE + f.key) || ''
  } catch {
    return ''
  }
}

function keep(f: Field, v: string): void {
  if (!f.remember) return
  try {
    window.localStorage.setItem(STORE + f.key, v)
  } catch {
    /* private window: not remembered */
  }
}

/** A message written from a plan, shown so it can be changed before it is
 *  copied. It sends nothing: the person pastes it into WhatsApp or an email. */
export function MessageComposer({
  title,
  intro,
  fields,
  build,
  onClose,
  notice,
  onCopied,
  markLabel,
}: {
  title: string
  intro: string
  fields: Field[]
  build: (values: Record<string, string>) => string
  onClose: () => void
  /** Something to say above the text, e.g. that a step has no shot list. */
  notice?: string
  /** After a copy: offer to record that it was asked of the first field's name. */
  onCopied?: (values: Record<string, string>) => Promise<{ ok: boolean; message: string }>
  markLabel?: string
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, recall(f)])),
  )
  const [edited, setEdited] = useState<string | null>(null) // the text, once she has changed it herself
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const [marked, setMarked] = useState<string | null>(null) // set once it worked
  const [markNote, setMarkNote] = useState<string | null>(null) // why it did not
  const generated = useMemo(() => build(values), [build, values])
  const text = edited ?? generated

  return (
    <div className="space-y-3 rounded-lg border border-yel/30 bg-bg2 p-3" data-testid="message-composer">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-tx">{title}</p>
          <p className="text-xs text-tx3">{intro}</p>
        </div>
        <button type="button" onClick={onClose} className="text-xs text-tx3 hover:text-tx" aria-label="Close">
          Close
        </button>
      </div>
      <div className="flex flex-wrap gap-3">
        {fields.map((f) => (
          <label key={f.key} className="block min-w-0 flex-1 basis-40 text-xs text-tx2">
            {f.label}
            <input
              data-testid={`composer-${f.key}`}
              className="mt-1 block w-full rounded border border-bd bg-bg px-2 py-1 text-sm text-tx"
              placeholder={f.placeholder}
              value={values[f.key] || ''}
              onChange={(e) => {
                keep(f, e.target.value)
                setValues((v) => ({ ...v, [f.key]: e.target.value }))
                setStatus('idle')
              }}
            />
          </label>
        ))}
      </div>
      {notice ? (
        <p className="rounded border border-yel/30 bg-yel/10 px-2 py-1 text-xs text-yel" data-testid="composer-notice">
          {notice}
        </p>
      ) : null}
      <textarea
        aria-label="The message"
        data-testid="composer-text"
        className="block h-72 w-full rounded border border-bd bg-bg px-2 py-2 text-sm leading-relaxed text-tx"
        value={text}
        onChange={(e) => {
          setEdited(e.target.value)
          setStatus('idle')
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="composer-copy"
          onClick={async () => setStatus((await copyText(text)) ? 'copied' : 'failed')}
          className="rounded-full border border-yel/40 bg-yel/15 px-4 py-1.5 text-xs font-semibold text-yel hover:bg-yel/25"
        >
          Copy message
        </button>
        {edited !== null ? (
          <button
            type="button"
            onClick={() => {
              setEdited(null)
              setStatus('idle')
            }}
            className="rounded-full border border-bd px-3 py-1.5 text-xs font-semibold text-tx2 hover:text-tx"
          >
            Start the message again
          </button>
        ) : null}
        {status === 'copied' ? (
          <span className="text-xs text-emerald-400" data-testid="composer-status">
            Copied. Paste it into WhatsApp or an email.
          </span>
        ) : null}
        {status === 'failed' ? (
          <span className="text-xs text-red" data-testid="composer-status">
            Could not copy. Select the text above and copy it yourself.
          </span>
        ) : null}
        {status === 'copied' && onCopied && marked === null ? (
          <button
            type="button"
            data-testid="composer-mark"
            onClick={async () => {
              const r = await onCopied(values)
              if (r.ok) setMarked(r.message)
              else setMarkNote(r.message)
            }}
            className="rounded-full border border-bd px-3 py-1.5 text-xs font-semibold text-tx2 hover:text-tx"
          >
            {markLabel || 'I have sent it: mark as asked'}
          </button>
        ) : null}
        {markNote && marked === null ? (
          <span className="text-xs text-red" data-testid="composer-mark-note">
            {markNote}
          </span>
        ) : null}
        {marked ? (
          <span className="text-xs text-emerald-400" data-testid="composer-marked">
            {marked}
          </span>
        ) : null}
      </div>
    </div>
  )
}
