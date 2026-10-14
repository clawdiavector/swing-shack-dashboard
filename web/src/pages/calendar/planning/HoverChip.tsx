import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export const CARD_W = 256

/** Where the card sits: under the chip, kept inside the screen, flipped above
 *  when there is no room below. Fixed to the viewport, so it is not clipped by
 *  the grid or the glass panel around it. */
export function cardPosition(
  chip: { left: number; top: number; bottom: number },
  viewport: { w: number; h: number; x?: number },
  cardH = 190,
): { left: number; top: number } {
  const x = viewport.x ?? 0
  const left = Math.max(x + 8, Math.min(chip.left, x + viewport.w - CARD_W - 8))
  const below = chip.bottom + 4
  const top = below + cardH > viewport.h ? Math.max(8, chip.top - cardH - 4) : below
  return { left, top }
}

/** A small chip that opens a card on hover, focus or tap. The card is drawn in
 *  a portal so it is never clipped by the month grid. */
export function HoverChip({
  chip,
  chipClass,
  chipTestId,
  cardTestId,
  cardLabel,
  children,
}: {
  chip: ReactNode
  chipClass: string
  chipTestId: string
  cardTestId: string
  cardLabel: string
  children: ReactNode
}) {
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const chipRef = useRef<HTMLSpanElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const timer = useRef<number | undefined>(undefined)
  const open = pos !== null

  // The visual viewport is what the person sees; it is narrower than the
  // layout viewport when the page overflows sideways.
  const viewport = () => {
    const vv = window.visualViewport
    return vv
      ? { w: vv.width, h: vv.height, x: vv.offsetLeft }
      : { w: window.innerWidth, h: window.innerHeight }
  }

  const show = () => {
    window.clearTimeout(timer.current)
    const r = chipRef.current?.getBoundingClientRect()
    if (r) setPos(cardPosition(r, viewport()))
  }

  // Cards differ in height (the plan step card has an edit section), so once one
  // is drawn, place it again using its real height.
  const shown = pos !== null
  useLayoutEffect(() => {
    const card = cardRef.current
    const r = chipRef.current?.getBoundingClientRect()
    if (!shown || !card || !r) return
    const next = cardPosition(r, viewport(), card.offsetHeight)
    setPos((cur) => (cur && (Math.abs(cur.top - next.top) > 2 || Math.abs(cur.left - next.left) > 2) ? next : cur))
  }, [shown])
  const hideSoon = () => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setPos(null), 180)
  }

  useEffect(() => {
    if (!open) return
    const close = () => setPos(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  return (
    <span className="block" onMouseEnter={show} onMouseLeave={hideSoon} onFocus={show}>
      <span
        ref={chipRef}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        data-testid={chipTestId}
        onClick={(e) => {
          e.stopPropagation()
          if (open) setPos(null)
          else show()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            e.stopPropagation()
            if (open) setPos(null)
            else show()
          }
          if (e.key === 'Escape') setPos(null)
        }}
        className={chipClass}
      >
        {chip}
      </span>
      {pos
        ? createPortal(
            <div
              ref={cardRef}
              role="dialog"
              aria-label={cardLabel}
              data-testid={cardTestId}
              onClick={(e) => e.stopPropagation()}
              onMouseEnter={() => window.clearTimeout(timer.current)}
              onMouseLeave={hideSoon}
              style={{ position: 'fixed', left: pos.left, top: pos.top, width: CARD_W }}
              className="z-50 space-y-2 rounded-xl border border-bd bg-bg2 p-3 text-left shadow-xl"
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </span>
  )
}
