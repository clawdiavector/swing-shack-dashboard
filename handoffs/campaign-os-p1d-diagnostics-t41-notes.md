# t41 watch upgrade — handoff (not landed in this repo)

**Status:** PARTIAL / code prepared, not merged to agent-control `main`.
**Still:** `--no-agent`, R0, exit 0 always, silent when all OK.
**Patch:** `handoffs/campaign-os-p1d-diagnostics-t41-watch.patch` (against
`agent-control` worktree `feat/campaign-os-p0c-ac`).

## What changed

- `bin/campaign_os_jobs_lib.py`: `format_bad_alert(..., failures=)` adds
  `error_class` + `↳` top suggested check; `fetch_jobs_failures()` calls
  `GET /api/jobs/failures` and returns `None` on any error (P0c line kept).
- `bin/watch_campaign_os.py`: on non-OK alert path only, fetch failures for
  enrichment. Healthy path still one request (`/api/jobs/status`).

## Shim note (t41-E)

Installed Hermes shims still point at the unmerged
`feat/campaign-os-p0c-ac` worktree. Merging p0c-ac → agent-control `main`,
landing this patch there, then repointing shims to
`/home/kyle/finder-workspace/repos/work/agent-control/bin/…` is required
before t41 is fully live. `~/.hermes/scripts/` was **not** edited by this job.

## Apply

```bash
cd /home/kyle/finder-workspace/repos/work/agent-control  # or the p0c-ac worktree
git apply /path/to/campaign-os-p1d-diagnostics-t41-watch.patch
```
