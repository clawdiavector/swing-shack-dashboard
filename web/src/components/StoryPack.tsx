import { useState } from 'react'

// "Make a story": a short headline and a caption to edit and copy. No image yet; the person adds
// their own photo in the story app. Nothing is saved or posted from here.

export const MAX_HEADLINE = 40

/** A headline from a caption line when none was drafted: the first sentence, cut at a word at 40 characters. */
export function deriveHeadline(line: string, max = MAX_HEADLINE): string {
  const first = (line.split(/(?<=[.!?])\s/)[0] ?? '').replace(/[.!?]+$/, '').trim()
  if (first.length <= max) return first
  const cut = first.slice(0, max + 1)
  const space = cut.lastIndexOf(' ')
  return (space > 10 ? cut.slice(0, space) : first.slice(0, max)).replace(/[,;:\-–]+$/, '').trim()
}

type CopyKind = 'headline' | 'caption' | 'both'

type ViewProps = {
  open: boolean
  headline: string
  caption: string
  copied: CopyKind | null
  onToggle: () => void
  onHeadline: (v: string) => void
  onCaption: (v: string) => void
  onCopy: (kind: CopyKind) => void
}

const btn = 'rounded-full border border-white/15 px-3 py-1 text-xs font-semibold hover:border-ac hover:text-ac'

export function StoryPackView(p: ViewProps) {
  if (!p.open) {
    return (
      <button type="button" className={`${btn} mt-2 text-tx`} onClick={p.onToggle}>
        Make a story
      </button>
    )
  }
  const over = p.headline.length > MAX_HEADLINE
  return (
    <div className="mt-2 rounded-xl border border-yel/40 bg-yel/10 p-3 text-sm">
      <label className="block text-xs font-semibold text-tx2" htmlFor="story-headline">
        Story headline{' '}
        <span className={over ? 'text-red' : 'text-tx3'}>
          ({p.headline.length}/{MAX_HEADLINE})
        </span>
      </label>
      <input
        id="story-headline"
        value={p.headline}
        onChange={(e) => p.onHeadline(e.target.value)}
        className="mt-1 w-full rounded-lg border border-white/15 bg-transparent px-3 py-2 text-tx"
      />
      <label className="mt-3 block text-xs font-semibold text-tx2" htmlFor="story-caption">
        Caption
      </label>
      <textarea
        id="story-caption"
        value={p.caption}
        onChange={(e) => p.onCaption(e.target.value)}
        rows={3}
        className="mt-1 w-full rounded-lg border border-white/15 bg-transparent px-3 py-2 text-tx"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" className={btn} onClick={() => p.onCopy('headline')}>
          {p.copied === 'headline' ? 'Copied' : 'Copy headline'}
        </button>
        <button type="button" className={btn} onClick={() => p.onCopy('caption')}>
          {p.copied === 'caption' ? 'Copied' : 'Copy caption'}
        </button>
        <button type="button" className={`${btn} bg-yel text-bg`} onClick={() => p.onCopy('both')}>
          {p.copied === 'both' ? 'Copied' : 'Copy both'}
        </button>
        <button type="button" className={`${btn} text-tx3`} onClick={p.onToggle}>
          Close
        </button>
      </div>
      <p className="mt-2 text-xs text-tx3">
        Paste into your story, over a real photo of your own. Nothing is saved or posted from here.
      </p>
    </div>
  )
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return
  } catch {
    // Fall back for browsers that block the clipboard API.
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    document.execCommand('copy')
  } finally {
    document.body.removeChild(ta)
  }
}

export function StoryPack({ headline, caption }: { headline: string; caption: string }) {
  const [open, setOpen] = useState(false)
  const [head, setHead] = useState(headline)
  const [cap, setCap] = useState(caption)
  const [copied, setCopied] = useState<CopyKind | null>(null)

  const onCopy = (kind: CopyKind) => {
    const text = kind === 'headline' ? head : kind === 'caption' ? cap : `${head}\n\n${cap}`
    void copyText(text).then(() => {
      setCopied(kind)
      window.setTimeout(() => setCopied(null), 2000)
    })
  }

  return (
    <StoryPackView
      open={open}
      headline={head}
      caption={cap}
      copied={copied}
      onToggle={() => setOpen((v) => !v)}
      onHeadline={setHead}
      onCaption={setCap}
      onCopy={onCopy}
    />
  )
}
