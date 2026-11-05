// "OK" only says a job ran. /api/jobs/status adds data_stale when the files it writes are still old
// (campaign-os/_lib/jobs/data_freshness.py; audit, 3 Nov 2026).

export type JobDataFields = {
  data_stale?: boolean
  data?: { file?: string; age_days?: number; newest_at?: string } | null
}

export function staleDataNote(job: JobDataFields): string {
  if (!job.data_stale || !job.data) return ''
  const days = Math.round(job.data.age_days ?? 0)
  return `Runs OK, but its data is ${days} day${days === 1 ? '' : 's'} old (${job.data.file}).`
}
