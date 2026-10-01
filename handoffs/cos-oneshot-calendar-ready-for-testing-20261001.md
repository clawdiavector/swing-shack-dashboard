# Calendar day desk — ready for testing

**Date:** 2026-10-01  
**Job:** `job-20261001-cos-oneshot-calendar-ready-for-testing`  
**Run:** `20261001T185325-ready-for-testing-da6f22`  
**Branch:** `feat/cos-oneshot-calendar`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-calendar`

## Commit under test

- **Feature commit (product code):** `0df245cabfb0a280b3cdf009504b21ebb53dd03d` — `feat(calendar): day desk render_mode on /app/week`
- **Pushed branch tip:** `226239a8d28a5358abc8e6c2cdd6807f7efe880a` (`origin/feat/cos-oneshot-calendar` at ready-for-testing finish)

## Verification (worker)

From `campaign-os/` with scratch `DATA_DIR` and bundled seed data:

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-calendar
export BUNDLED_DATA_DIR="$WT/data" DATA_DIR=$(mktemp -d) COS_JOB_TOKEN=dev-token
cd "$WT/campaign-os"
python3 -m pytest tests/test_render_mode_day_desk_20261002.py -q
cd "$WT/web"
npm test -- --run postingWeek.test.ts
npm run build
```

Local smoke (job port **3856**):

```bash
export DATA_DIR=$(mktemp -d) BUNDLED_DATA_DIR="$WT/data" COS_JOB_TOKEN=dev-token PORT=3856
cd "$WT/campaign-os" && python3 app.py
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3856/api/health
```

**Result (2026-10-01 RFT):** `11 passed` day-desk pytest; `21 passed` postingWeek vitest; web `build` OK; `/api/health` → `200`.

## Scope

Day desk on Campaign Heroes **`/app/week`**: Today / Tomorrow / date picker, single-day load, `render_mode` (`template` | `oneshot`) on week-board rows, inline edit + moment PATCH. **No image generation** in this slice — mode is recorded for the next render only.

## Manual QA (local or post-land)

**URL:** `http://127.0.0.1:3856/app/week` (port from job file; session login if required on prod).

| # | Step | Expected |
|---|---|---|
| 1 | Open **`/app/week`** | Week board loads; intro mentions week or day desk |
| 2 | Click **Today** | URL gains `?tab=day&date=<SAST today>`; one day section; **Today** chip highlighted |
| 3 | Click **Tomorrow** | Date updates to tomorrow; posts for that day only |
| 4 | Use **date** input to pick another day | Day desk reloads for that ISO date |
| 5 | On a **candidate** (or other editable) post, click **Edit** | Inline panel: post type, title, angle, **Render mode** radios |
| 6 | Select **One-shot**, blur or tab out | Badge shows One-shot (yellow); save succeeds |
| 7 | Select **Template** again | Badge returns to Template; persisted after refresh |
| 8 | Click **Week** | Returns to multi-day week view (no `tab=day`) |

**Prod (after Kyle lands):** same paths on Railway `/app/week`.

## Push

Branch `feat/cos-oneshot-calendar` pushed to `origin` after verify PASS (feature + handoff commits). Do **not** push `main` / `develop` / `master`.
