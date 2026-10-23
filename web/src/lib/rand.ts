export function rand(n: number | null | undefined): string {
  if (n == null) return '—'
  const r = Math.round(n)
  return r < 0 ? `-R${Math.abs(r).toLocaleString('en-ZA')}` : `R${r.toLocaleString('en-ZA')}`
}
