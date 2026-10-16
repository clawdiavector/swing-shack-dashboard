// Helpers for "how old is this data" labels on the Results pages.

/** Whole days between now and an ISO timestamp or YYYY-MM-DD date, or null if unparseable. */
export function ageDays(iso?: string | null): number | null {
  if (!iso) return null
  const t = Date.parse(iso.length === 10 ? `${iso}T00:00:00` : iso)
  if (Number.isNaN(t)) return null
  return Math.floor((Date.now() - t) / 86_400_000)
}

/** The YYYY-MM-DD part of an ISO timestamp, or '' when missing. */
export function dateOnly(iso?: string | null): string {
  return iso ? iso.slice(0, 10) : ''
}
