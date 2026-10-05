# ClubLab pull — implement handoff (2026-10-05)

**Branch:** `feat/cos-clublab-pull`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Run:** `20261005T080733-implement-3429b1`

## Unit tests

```text
pytest campaign-os/tests/test_clublab_pull.py -v → 5 passed
```

## CoachMe route confirmation

CoachMe confirmed at `GET /api/v1/Reports/session-summary` and `GET /api/v1/Reports/tag-frequency` (ASP.NET `[Route("api/v1/[controller]")]` → `ReportsController`).

## Live pull

Attempted once via `campaign-os/scripts/live_pull.py` with `credentials-external.env` sourced into the environment (`DATA_DIR` scratch under `/tmp`).

**Result:** failed before any facility GET.

| Field | Value |
|---|---|
| HTTP status | 401 |
| Endpoint | `https://clublab.app/api/v1/auth/login` |
| Cause | After sourcing `credentials-external.env`, only `CLUBLAB_PASSWORD` was present — no `CLUBLAB_EMAIL` or `CLUBLAB_TOKEN` in that file or the shell environment. Login was not attempted with a complete credential pair. |

No facility counts recorded (no invented numbers).

## Notes

- Mocked HTTP unit tests cover the pull path and deny-list.
- Re-run live pull after `CLUBLAB_EMAIL` (or `CLUBLAB_TOKEN`) is available alongside the password file.
