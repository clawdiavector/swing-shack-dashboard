# Schedule a day — ready for testing

**Date:** 2026-10-01  
**Job:** `job-20261001-cos-oneshot-schedule-ready-for-testing`  
**Run:** `20261001T200537-ready-for-testing-962188`  
**Branch:** `feat/cos-oneshot-schedule`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-schedule`

## Commit under test

- **Feature commit (product code):** `4273fa0d4710583c896bbae1bb70f4db3cc9619c` — `feat(calendar): schedule empty day with candidate batch`
- **Pushed branch tip:** update after this handoff commit (`git rev-parse HEAD` on `origin/feat/cos-oneshot-schedule`)

## Verification (prior verify job)

Verify tier **light** — **6/6 acceptance criteria PASS** against feature tip `4273fa0d`.

From `campaign-os/` with scratch `DATA_DIR` and bundled seed data:

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-schedule
export BUNDLED_DATA_DIR="$WT/data" DATA_DIR=$(mktemp -d) COS_JOB_TOKEN=dev-token

cd "$WT/campaign-os"
python3 -m pytest \
  tests/test_day_schedule_batch_20261002.py \
  tests/test_render_mode_day_desk_20261002.py \
  tests/test_meme_lord_v2.py \
  -q
python3 -m pytest tests/test_v2026_08_07_socials_meme_visuals.py -q

cd "$WT/web"
npm test -- --run postingWeek.test.ts
npm run build
```

**Spot check (RFT worker):** `9 passed` in `test_day_schedule_batch_20261002.py` on `4273fa0d`.

Local smoke (job port **3489**):

```bash
export DATA_DIR=$(mktemp -d) BUNDLED_DATA_DIR="$WT/data" COS_JOB_TOKEN=dev-token PORT=3489
cd "$WT/campaign-os" && python3 app.py
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3489/api/health
```

## Scope

Day desk **`/app/week`** (day mode): **Schedule this day** on an empty SAST day calls `POST /api/calendar/schedule-day` per brand in scope. Writes **four candidate cards** per brand (no image generation, no Create enqueue). Exactly **one** card per brand has `render_mode: oneshot`; the rest are template. Stick one-shot type rotates by date (`fitting_headline`, `service_hero`, `coaching_promo`, `humour_card`, …).

**Flavour knob (taste, not measured):** humour cards default to `sarcastic` for both brands (`MEME_FLAVOUR_BY_BRAND` in `_lib/meme_lord.py`). Override per API call with body `flavour` if Kyle wants `hard-truth` / `wholesome` on Stick.

**Known rough edge:** `apply_meme` captions can mention Swing Shack items on Stick humour cards — stored verbatim; edit **Angle** on the day desk if needed (see plan §5.4).

## Manual QA (local or post-land)

**URL:** `http://127.0.0.1:3489/app/week` (port from job file; session login if required on prod).

| # | Step | Expected |
|---|---|---|
| 1 | Open **`/app/week`**, click **Tomorrow** (or pick a **date** with no posts for your brand) | Day section shows **Nothing going out.** and **Schedule this day** |
| 2 | Click **Schedule this day** | Success line (e.g. counts per brand); day reloads with **4** cards, all **Candidate · no image yet** |
| 3 | Scan the four cards | Exactly **one** yellow **One-shot** badge per brand; others **Template** |
| 4 | Confirm post types | Template cards include daily-pillar rows; one-shot type matches brand rotation for that date (Stick cycles; Swing Shack one-shot is `fitting_headline` on a fresh plan) |
| 5 | Find the **humour card** when rotation lands on it (Stick: every fourth slot in rotation — try another empty day if today’s one-shot is not humour) | Title like **Humour card — …** (meme name); badge **One-shot** |
| 6 | Click **Edit** on that humour card | **Angle** shows the meme caption line (same text stored in `meme.caption` — not model-generated) |
| 7 | Click **Schedule this day** again on the same day | Message **already has posts** (409); day unchanged unless you force via API |
| 8 | **All brands** scope: empty day, schedule once | Both brands fill; partial errors surface in the status line if one brand was not empty |

**Prod (after Kyle lands):** same flow on Railway `/app/week`.

## Push

Branch `feat/cos-oneshot-schedule` pushed to `origin` after verify PASS and this handoff commit. Do **not** push `main` / `develop` / `master`.
