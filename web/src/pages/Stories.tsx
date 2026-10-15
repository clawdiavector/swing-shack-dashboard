import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'
import '../fun.css'
import { useBrand, useBrandScope } from '../components/BrandSwitch'
import { PageIntro } from '../components/chrome'
import { Chomper } from '../components/fun'
import { StoryReposts } from '../components/StoryReposts'
import { submitStoryLink } from '../lib/api'
import { toneFor } from '../lib/brandTone'
import { burstConfetti } from '../lib/confetti'

const STORY_BRANDS = ['swing-shack', 'stick', 'bag-drop']
const TONE_MAP = { gold: 'gold', green: 'green', blue: 'blue', red: 'violet' } as const
const HOSTS = ['instagram.com', 'instagr.am', 'facebook.com', 'fb.com', 'fb.watch', 'fb.me']

/** Mirrors the server's rule so the chomper can say no before asking. */
function pick<T>(list: T[]): T {
  return list[Math.floor(Math.random() * list.length)]
}

const CHOMPS = [
  (b: string) => `Chomp! Safe on the ${b} shelf.`,
  (b: string) => `Nom nom. That's on the ${b} shelf now.`,
  (b: string) => `Delicious. ${b} shelf, sorted.`,
  (b: string) => `Gulp. Tucked onto the ${b} shelf.`,
]

function linkProblem(raw: string): string {
  const text = raw.trim()
  if (!text) return 'I’m hungry. Paste a link first.'
  let host = ''
  try {
    host = new URL(text.includes('://') ? text : `https://${text}`).hostname.toLowerCase()
  } catch {
    return 'Mmm, that doesn’t taste like a link.'
  }
  return HOSTS.some((h) => host === h || host.endsWith(`.${h}`))
    ? ''
    : 'I only eat Instagram and Facebook links. Picky, I know.'
}

export function Stories() {
  const { brands } = useBrand()
  const { isAll, brandIds } = useBrandScope()
  const [url, setUrl] = useState('')
  const [note, setNote] = useState('')
  const [brand, setBrand] = useState('')
  const [state, setState] = useState<'idle' | 'hungry' | 'munch' | 'nope'>('idle')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)
  const [shake, setShake] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const mouthRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const choices = STORY_BRANDS.map((id) => {
    const row = brands.find((b) => b.id === id)
    const label = row?.label || id.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    return { id, label, tone: TONE_MAP[row?.tone ?? toneFor(id, label, 0)] }
  })

  // When the desk is on one brand, that brand is the default pick.
  useEffect(() => {
    if (!isAll && brandIds.length === 1 && STORY_BRANDS.includes(brandIds[0])) setBrand(brandIds[0])
  }, [isAll, brandIds])

  // Paste a link anywhere on the page and it lands in the box.
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return
      const text = e.clipboardData?.getData('text')?.trim()
      if (!text || !/^(https?:\/\/|[\w.-]+\.[a-z]{2,}\/)/i.test(text)) return
      e.preventDefault()
      setUrl(text)
      setMsg(null)
      setState('hungry')
      inputRef.current?.focus()
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  }, [])

  function say(kind: 'ok' | 'error', text: string) {
    setMsg({ kind, text })
  }

  function refuse(text: string) {
    say('error', text)
    setState('nope')
    setShake(true)
    setTimeout(() => {
      setState('idle')
      setShake(false)
    }, 450)
  }

  async function feed(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const problem = linkProblem(url)
    if (problem) return refuse(problem)
    if (!brand) return refuse('Who’s this one for? Pick a brand.')
    setBusy(true)
    setMsg(null)
    setState('hungry')
    try {
      const res = await submitStoryLink({ brand, url: url.trim(), note: note.trim() })
      if (!res.ok) return refuse(res.error || 'I choked on that one. Try again?')
      const label = choices.find((c) => c.id === brand)?.label || brand
      if (res.created) {
        setState('munch')
        const r = mouthRef.current?.getBoundingClientRect()
        if (r) burstConfetti(r.left + r.width * 0.12, r.top + r.height / 2, 60)
        say('ok', pick(CHOMPS)(label))
        setUrl('')
        setNote('')
        setRefresh((n) => n + 1)
        setTimeout(() => setState('idle'), 1300)
      } else {
        refuse(`Burp. I already ate that one. It’s on the ${label} shelf.`)
      }
    } catch {
      refuse('I choked. Give me a minute and try again.')
    } finally {
      setBusy(false)
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    const text = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')).trim()
    if (text) {
      setUrl(text)
      setMsg(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro here="/stories" title="Stories">
        Found a good post? Feed me the link and it’s on the shelf, ready to share to Stories.
      </PageIntro>

      <div
        ref={mouthRef}
        className="fun-mouth"
        data-over={over ? 'true' : undefined}
        data-shake={shake ? 'true' : undefined}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
          setState('hungry')
        }}
        onDragLeave={() => {
          setOver(false)
          setState('idle')
        }}
        onDrop={onDrop}
      >
        <Chomper state={state} />
        <form onSubmit={feed} noValidate>
          <h2>Drop a link. I’ll eat it up.</h2>
          <div className="fun-mouth__row">
            <input
              ref={inputRef}
              id="story-link"
              type="url"
              inputMode="url"
              autoComplete="off"
              placeholder="Paste a link here"
              aria-label="Instagram or Facebook link"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value)
                setMsg(null)
              }}
              onFocus={() => setState('hungry')}
              onBlur={() => setState((s) => (s === 'hungry' ? 'idle' : s))}
            />
            <button className="fun-mouth__go" type="submit" disabled={busy}>
              {busy ? 'Chewing…' : 'Feed it'}
            </button>
          </div>
          <div className="fun-pick" role="group" aria-label="Which brand is this for?">
            <span>Who’s it for?</span>
            {choices.map((c) => (
              <button
                key={c.id}
                type="button"
                data-tone={c.tone}
                aria-pressed={brand === c.id}
                onClick={() => {
                  setBrand(c.id)
                  setMsg(null)
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
          <div className="fun-mouth__row" style={{ marginTop: '0.7rem' }}>
            <input
              id="story-note"
              type="text"
              maxLength={280}
              autoComplete="off"
              placeholder="A note for the sharer (optional)"
              aria-label="Note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <p className="fun-mouth__msg" data-kind={msg?.kind} role="status">
            {msg?.text ?? 'Instagram and Facebook only, I’m picky. Paste anywhere on this page and I’ll find it.'}
          </p>
        </form>
      </div>

      <StoryReposts brandIds={isAll ? undefined : brandIds} refreshKey={refresh} alwaysShow />
    </div>
  )
}
