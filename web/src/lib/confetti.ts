const CONFETTI = ['#fbbf24', '#34d399', '#60a5fa', '#a855f7', '#f87171']

/** One-shot confetti. Makes its own canvas, removes it when the last piece fades. */
export function burstConfetti(x: number, y: number, count = 60) {
  if (typeof document === 'undefined') return
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  const cv = document.createElement('canvas')
  cv.width = window.innerWidth
  cv.height = window.innerHeight
  cv.setAttribute('aria-hidden', 'true')
  cv.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:90'
  document.body.appendChild(cv)
  const cx = cv.getContext('2d')
  if (!cx) {
    cv.remove()
    return
  }
  let ps = Array.from({ length: count }, (_, i) => {
    const a = Math.random() * Math.PI * 2
    const s = 3 + Math.random() * 7
    return {
      x,
      y,
      vx: Math.cos(a) * s,
      vy: Math.sin(a) * s - 4,
      r: 3 + Math.random() * 5,
      c: CONFETTI[i % CONFETTI.length],
      l: 60 + Math.random() * 30,
      rot: Math.random() * 6,
    }
  })
  const tick = () => {
    cx.clearRect(0, 0, cv.width, cv.height)
    ps = ps.filter((p) => p.l > 0)
    for (const p of ps) {
      p.x += p.vx
      p.y += p.vy
      p.vy += 0.25
      p.vx *= 0.99
      p.l -= 1
      p.rot += 0.2
      cx.save()
      cx.translate(p.x, p.y)
      cx.rotate(p.rot)
      cx.fillStyle = p.c
      cx.globalAlpha = Math.min(1, p.l / 30)
      cx.fillRect(-p.r, -p.r / 2, p.r * 2, p.r)
      cx.restore()
    }
    if (ps.length) requestAnimationFrame(tick)
    else cv.remove()
  }
  requestAnimationFrame(tick)
}
