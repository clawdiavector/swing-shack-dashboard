export function sumCounts<T extends Record<string, number | undefined>>(
  list: (T | undefined)[],
): T {
  const out = {} as T
  for (const row of list) {
    if (!row) continue
    for (const [key, val] of Object.entries(row)) {
      if (typeof val !== 'number') continue
      const k = key as keyof T
      const prev = out[k]
      const n = typeof prev === 'number' ? prev : 0
      ;(out as Record<string, number>)[key] = n + val
    }
  }
  return out
}
