import { useCallback, useRef } from 'react'

/** Await in-flight fan-out reads before inbox/release writes (plan §3.5). */
export function useLoadGate() {
  const inflight = useRef<Promise<void> | null>(null)

  const trackLoad = useCallback((promise: Promise<void>) => {
    inflight.current = promise
    void promise.finally(() => {
      if (inflight.current === promise) inflight.current = null
    })
  }, [])

  const waitForLoad = useCallback(async () => {
    const p = inflight.current
    if (p) await p.catch(() => undefined)
  }, [])

  return { trackLoad, waitForLoad }
}
