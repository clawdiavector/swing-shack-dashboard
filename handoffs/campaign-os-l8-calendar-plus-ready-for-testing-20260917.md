# Ready for testing: Campaign OS L8 — Calendar+ (tL8-1 + tL8-2)

**Date:** 2026-09-17  
**Job:** `job-20260917-campaign-os-l8-calendar-plus-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260917-campaign-os-l8-calendar-plus-verify` (Pi, read-only)  
**Verify verdict:** **PASS** — `20260917T132756-review-f06b6f` @ `20d6074`: swing-shack `calendar_config.json` schema matches stick contract; `holiday_inject` idempotent upsert, no network; **14/14** config + holiday tests; 2 `suggested_checks` failures pre-existing on base  
**Plan:** `agent-control/manifests/plan-20260917-campaign-os-l8-calendar-plus.yaml` + `agent-control/handoffs/campaign-os-layers/L8-calendar-plus.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l8-calendar-plus`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

L8 Calendar+ slice (tL8-1 + tL8-2): committed `data/brand-directory/swing-shack/calendar_config.json` (stick-shaped schema, K10 pillar placeholders) and registered `holiday_inject` JobSpec — deterministic SA public holidays → calendar records with `source_origin=deterministic_calendar`, idempotent via existing marketing calendar write path. Verify **PASS**. Feat branch **on origin**.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `20d6074e37b45a8acacc49450ab969a58a57a959` |
| Short | `20d6074` |
| Origin tip | `origin/feat/campaign-os-l8-calendar-plus` @ `20d6074`+handoff (pushed by RFT job) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `4547245` |
| Feat merge-base with integrate | `86b8a20` (1 commit on feat) |
| RFT handoff commit | lands after this file (see git log) |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-l8-calendar-plus` | **YES** @ `20d6074`+handoff | RFT pushes code tip then handoff doc. |

## RFT re-verify (this job)

Fresh pytest on scoped L8 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_holiday_inject.py tests/test_l8_swing_shack_calendar_config.py -q
```

**Result:** `14 passed, 0 failed` (2026-09-17, RFT job).

Extended L2 registry smoke (same SHA):

```bash
python3 -m pytest tests/jobs/test_layer2_jobs.py -q
```

**Result:** `27 passed, 0 failed` (includes `holiday_inject` registration + description).

Pi verify reported **14p/0f** on config + holiday tests at the same SHA — counts match.

## Done-when (L8-calendar-plus.md — this slice only)

| Criterion | Status | Evidence |
|---|---|---|
| `data/brand-directory/swing-shack/calendar_config.json` exists (tL8-1) | **PASS** | `test_swing_shack_config_loads_configured`; `/api/calendar/section/swing-shack` → 200 |
| Schema matches stick shape (pillars, lead_time, scouting_profile) | **PASS** | Pi verify schema diff; pillar colours disjoint from stick |
| North-star placeholders marked `canonical=false` (K10 pending) | **PASS** | `test_north_star_placeholders_marked_non_canonical` |
| Job `holiday_inject` registered in L2 layer | **PASS** | `test_holiday_inject_registered`; `layer2/__init__.py` |
| SA public holidays → calendar records, `source_origin=deterministic_calendar` | **PASS** | `test_holiday_records_have_deterministic_origin` |
| Idempotent upsert (second run no dupes) | **PASS** | `test_holiday_inject_idempotent` |
| No network / no Firecrawl / no keys | **PASS** | stdlib-only Easter + fixed civil dates; verify grep |
| Extends `marketing_calendar.py` — no second calendar | **PASS** | uses existing write path via `_lib.marketing_calendar` |

**Out of scope (not RFT blockers — later L8 tickets or human gates):**

| Criterion | Status | Notes |
|---|---|---|
| Christelle pillar copy + north-star targets (K10) | **CHECKLIST BELOW** | Config ships with `PENDING CHRISTELLE (K10)` placeholders — **post-land review** |
| Mothership V2 schema migration (K11) | **DEFERRED** | tL8-4 — do not implement until spec approved |
| Holiday overlay UX (tL8-3) | **DEFERRED** | SPA month overlay — separate ticket |
| Link moment → campaign container (tL8-5) | **DEFERRED** | Needs K11 + L4 approve path |
| `test_suggested_checks.py` (2 failures) | **PRE-EXISTING RED** | Red at base `86b8a20`; not in CI allowlist — not attributed to L8 |

## Manual tests — swing-shack calendar + `holiday_inject`

Environment: local worktree, scratch `$DATA_DIR`, port from job file **`3387`**. Bearer for job run; session for calendar section. Never print secret values.

| # | Step | Expected |
|---|---|---|
| 1 | Start app: `cd campaign-os && DATA_DIR=/tmp/cos-l8-manual COS_JOB_TOKEN=local-dev PORT=3387 python3 app.py` | Health OK |
| 2 | Log in → `GET /api/calendar/section/swing-shack` | `200`; configured pillars visible; no “not configured yet” banner |
| 3 | Compare pillar count vs stick (reference) | SS has distinct pillar IDs (`ss-fitting`, `ss-coaching`, …); colours ≠ stick palette |
| 4 | Bearer `POST /api/jobs/run/holiday_inject?reason=manual` | Job OK; calendar records written under `$DATA_DIR` |
| 5 | Re-run step 4 | Same record count (idempotent); no duplicate Heritage Day rows |
| 6 | Inspect one holiday record | `source_origin == "deterministic_calendar"`, `created_by == "holiday_inject"` |
| 7 | Confirm **nothing published** | No Postiz dispatch; no new publish receipts |

Optional eyeball URLs (port **3387**):

```bash
# calendar section API (session):
#   http://127.0.0.1:3387/api/calendar/section/swing-shack
# job status after inject:
#   curl -H "Authorization: Bearer $COS_JOB_TOKEN" http://127.0.0.1:3387/api/jobs/status
```

Automated coverage: `test_holiday_inject.py` + `test_l8_swing_shack_calendar_config.py` exercise steps 2–6 without a dev server (monkeypatched `$DATA_DIR`).

## Christelle pillar review checklist (K10 — post-integrate)

**Target:** Christelle reviews swing-shack pillar definitions and north-star targets after land. **Do not block land** — placeholders are intentional until K10 sign-off.

| # | Step | Pass? | Notes |
|---|---|---|---|
| 1 | Open `data/brand-directory/swing-shack/calendar_config.json` | ☐ | Five pillars: Fitting, Coaching, Membership, Events, Retail |
| 2 | Pillar names match Swing Shack operating model | ☐ | Rename/adjust `pillar_id` only if Christelle specifies |
| 3 | Replace `PENDING CHRISTELLE (K10)` objectives | ☐ | One sentence per pillar |
| 4 | Set north-star targets (`daily_volume`, ZAR where applicable) | ☐ | Flip `source_provenance` to `canonical=true` when locked |
| 5 | Confirm pillar colours in SPA calendar month view | ☐ | Distinct from stick/bag-drop; readable on dark UI |
| 6 | Confirm `major_retail` lead time (90-day research) fits SS retail cadence | ☐ | Adjust `lead_time_rules` if needed |
| 7 | Run `holiday_inject` on preview/staging | ☐ | Holidays appear on calendar; no scout duplicates |
| 8 | Sign-off recorded (date + initials) | ☐ | Kyle tracks K10 in programme board |

Record outcome in a follow-up note (date, pass/fail per row, blockers). This handoff supplies the checklist only; Christelle does not need to run before land.

## Commits on feat (vs merge-base `86b8a20`)

1. `20d6074` feat(calendar): tL8-1 swing-shack config + tL8-2 holiday_inject

## Files touched (product)

| Path | Change |
|---|---|
| `data/brand-directory/swing-shack/calendar_config.json` | **new** — SS brand calendar config (K10 placeholders) |
| `campaign-os/_lib/jobs/layer2/holiday_inject.py` | **new** — deterministic SA holiday inject |
| `campaign-os/_lib/jobs/layer2/__init__.py` | register `holiday_inject` JobSpec |
| `campaign-os/_lib/jobs/descriptions.py` | job description for ops digest |
| `campaign-os/tests/jobs/test_holiday_inject.py` | **new** — 8 contract tests |
| `campaign-os/tests/test_l8_swing_shack_calendar_config.py` | **new** — 6 schema/API tests |
| `campaign-os/tests/jobs/test_layer2_jobs.py` | `holiday_inject` in registry smoke |

## Job registered

| Job | Cadence | Criticality | best_effort | Writes |
|---|---|---|---|---|
| `holiday_inject` | 24h | LOW | yes | calendar records via marketing calendar path (`source_origin=deterministic_calendar`) |

Run manually: `POST /api/jobs/run/holiday_inject?reason=manual` (bearer or session).

## Open Kyle items

1. **Land** — next job merges `feat/campaign-os-l8-calendar-plus` → `integrate/campaign-os-option-c` (integration push OK; not `main`). Expect merge with newer integrate tip (`4547245` has L5/L7 — resolve in land job).
2. **Christelle K10 pillar review** — use checklist § above after land (or on preview).
3. **tL8-3..7** — holiday overlay UX, Mothership V2, moment→campaign link — separate tickets per L8-calendar-plus.md.

## Suggested board / comment draft

Campaign OS L8 Calendar+ (tL8-1 + tL8-2) ready for testing. `feat/campaign-os-l8-calendar-plus` @ `20d6074` on origin. Pi verify **PASS** (swing-shack config schema, holiday_inject idempotent, no network). RFT re-verify **14p/0f**. Christelle K10 pillar checklist in handoff (post-land). Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260917-campaign-os-l8-calendar-plus-land` — merge feat → integrate locally, push `integrate/campaign-os-option-c` only.
