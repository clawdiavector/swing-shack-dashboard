# Generate and regen one-shots — ready for testing

**Date:** 2026-10-01  
**Job:** `job-20261001-cos-oneshot-generate-ready-for-testing`  
**Run:** `20261001T211519-ready-for-testing-5acb6e`  
**Branch:** `feat/cos-oneshot-generate`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-generate`

## Commit under test

- **Pushed branch tip:** update after this handoff commit (`git rev-parse HEAD` on `origin/feat/cos-oneshot-generate`)
- **Feature commits (product code on branch):**
  - `feac5fcc` — `feat(oneshot): WIP generate/regen before integrate merge` (day action, `draft_oneshot`, Review meta, regen routing)
  - `48c33dd1` — `fix(oneshot): humour copy from meme.caption and meme.flavour`
  - `d047c42d` — `test(oneshot): model select Recraft operator-only routing`
- **Merged schedule slice:** `4273fa0d` / `78952382` (schedule empty day — see `handoffs/cos-oneshot-schedule-ready-for-testing-20261001.md`)

## No live image in this ticket

Automated verify **does not** call Krea, OpenRouter, Recraft, or any other image provider. Every test mocks the router or enqueues only.

**Kyle runs the first real generate** after landing (or locally with live keys). Image quality, legible typography, and actual spend are out of scope for this ready-for-testing job.

## Verification (worker, light tier)

From `campaign-os/` with scratch `DATA_DIR` and bundled seed data:

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-generate
export BUNDLED_DATA_DIR="$WT/data" DATA_DIR=$(mktemp -d) COS_JOB_TOKEN=dev-token

cd "$WT/campaign-os"
python3 -m pytest \
  tests/test_oneshot_routing.py \
  tests/test_creative_oneshot_model_select.py \
  tests/test_creative_oneshot_prompt_sections.py \
  tests/test_creative_oneshot_wire_prompt.py \
  tests/jobs/test_oneshot_cap.py \
  tests/jobs/test_draft_oneshot.py \
  tests/test_render_mode_day_desk_20261002.py \
  tests/test_day_schedule_batch_20261002.py \
  -q
python3 ../scripts/lint_brand_visual.py "$WT"

cd "$WT/web"
npm test -- --run postingWeek.test.ts
npm run build
```

Local smoke (job port **3311**):

```bash
export DATA_DIR=$(mktemp -d) BUNDLED_DATA_DIR="$WT/data" COS_JOB_TOKEN=dev-token PORT=3311
export CAMPAIGN_OS_MAX_IMAGES_PER_DAY=2
cd "$WT/campaign-os" && python3 app.py
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3311/api/health
```

**Result (2026-10-01 RFT):** `36 passed` oneshot-focused pytest; `stick` / `bag-drop` / `swing-shack` lint ok; `23 passed` postingWeek vitest; web `build` OK; `/api/health` → `200`.

**Broader plan §8.4 suites:** some failures are environmental or pre-existing on base (e.g. `test_layer5_create.py` without `OPENAI_API_KEY`, image route tests returning `403` without session auth, nav tool count drift in `test_v2026_08_07_nav_clarity.py`). They were **not** treated as regressions from this branch; the oneshot-focused set above is the RFT gate.

**Quota note:** `image_submit_quota` keys on **UTC** day while the day desk uses SAST — a generate at 01:00 SAST counts against the previous UTC day (same as template lane).

**Side effect:** marketer Image Lab paths now request `1024x1280` (4:5) where they previously sent `1024x1024` — intentional fix from the sizes commit; spot-check Image Lab after land if you use it often.

## Scope

- **`POST /api/oneshot/day`** — enqueue `draft_oneshot` for the one oneshot card on a brand/day; template cards skipped; caps enforced (`CAMPAIGN_OS_MAX_IMAGES_PER_DAY` + one oneshot submit per brand per UTC day).
- **L5 job** `_lib/jobs/layer5/draft_oneshot.py` — prompt from card copy (humour: `meme.caption` + `meme.flavour`), logo composite by default, `1024x1280`, no live call in tests.
- **Day desk** `/app/week` (day mode) — **Generate one-shots** when the day has at least one oneshot card and caps allow.
- **Review** — `meta.oneshot` on list + detail: model, provider, size, cost, literal line, collapsed `prompt_used`, regen count; **Regenerate** on a oneshot draft re-enqueues `draft_oneshot` (not `compose_post`).

## Manual QA — Kyle (first live generate)

**URL:** `http://127.0.0.1:3311/app/week` (port from job file; Railway `/app/week` after land). Session login on prod as usual.

Prerequisites: live image keys configured in `DATA_DIR` / tenant secrets; L5 runner or manual job run for queued rows.

| # | Step | Expected |
|---|---|---|
| 1 | Open **`/app/week`**, pick an **empty SAST day** (or use **Schedule this day** per schedule handoff) | Day shows candidates; exactly **one** card per brand has **One-shot** badge when scheduled |
| 2 | Optionally **Edit** a oneshot card — set headline/angle; for humour confirm **Angle** shows meme caption | Copy is on the card before generate |
| 3 | Click **Generate one-shots** | Status names enqueued oneshot card(s); template cards reported as skipped |
| 4 | Run L5 / wait for runner | **One** draft per brand oneshot in **Review**; no draft for template-only cards |
| 5 | Open that draft in **Review** | One-shot panel: model, provider, **1024x1280**, cost; **Literal line** quoted; **`prompt_used`** in collapsed details |
| 6 | Inspect the **image** (first live run) | Card line rendered; brand logo composited from asset (unless AI logo toggled) |
| 7 | **Generate one-shots** again same day | Refused when one-shot / image cap reached |
| 8 | Edit card title/headline on day desk, then **Regenerate** on the draft | Same draft updates (same asset id); new prompt; **Regenerated 1×** in panel |

## Push

Branch `feat/cos-oneshot-generate` pushed to `origin` after verify PASS and this handoff commit. Do **not** push `main` / `develop` / `master`.
