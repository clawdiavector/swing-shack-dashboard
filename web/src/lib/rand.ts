export function rand(n: number | null | undefined): string {
  return n == null ? '—' : `R${Math.round(n).toLocaleString('en-ZA')}`
}
