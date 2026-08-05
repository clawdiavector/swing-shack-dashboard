# Campaign OS · Overnight CTO Build — Status & Continuation

## Last update
2026-07-27 · CTO overnight build · MiniMax-M3 (continuation session)

## Overnight cron
- Job ID `da7bebf99c66`, hourly 22:00–10:00 SAST, 12 ticks, delivers to Discord origin.
- Each tick: reads this file, builds one major feature end-to-end (frontend + backend + UX), commits + pushes, appends status block.

## What is running right now
- **Server**: `python3 campaign-os/app.py` on port 8765 (PID 73081, alive)
- **Branch**: `feat/asset-state-engine` (local + remote at `0bf8dfa` — Step 105A deployment)
- **Working tree**: dirty (has uncommitted `intelligence.py` + `campaign-os.html` + `app.py` edits from previous session)
- **Live URL (last tunnel)**: `https://que-wesley-caribbean-dts.trycloudflare.com` (may be expired — re-launch with `cloudflared tunnel --url http://127.0.0.1:8765`)

## What is shipped (verified alive in browser)
- **Single SPA**: `campaign-os/campaign-os.html` (~75KB, dark modern design)
- **23 intelligence endpoints** under `/api/intel/<view>` — all 200
- **Universal search**: `/api/search?q=`
- **Sidebar nav**: 21 entries (Brief, Review, Publish, Calendar, Trends, Ideas, Performance, Learning, Hooks, Memes, Billboards, Captions, Headlines, CTAs, SEO, GBP, Reddit, FAQs, Postiz, Campaigns, Agents)
- **Morning Brief**: 4 stat cards + 🔥 Hot trends ticker + 6 widget cards (Do first / Needs review / Ready / Misses / SEO wins / Post today)
- **Calendar**: 56 slots across 14 days (4/day), today highlighted, prev/today/next nav
- **Performance**: live IG avg ER, top posts with real captions + engagement, SEO rising/falling/keywords, A/B tests, GA4 pages, **natural-language insights** ("'…' is performing 310% better than your Instagram average.")
- **Hook Bank**: 89 hooks in 3 buckets + formulas + ⚡ Generate 10 fresh from signals → works
- **Caption Studio**: bank + CTAs + per-asset **⚡ Generate 5 caption variants** → works (tested: returned real hook + body + CTA for `takomo-101t-hook-a`)
- **Trend Catcher**: 8 YouTube trending topics with TRENDING/COOLING pills, 4 competitor moves
- **Asset detail modal**: opens from review inbox with Approve / Reject / Revision / ⚡ Generate captions / 📮 Open in Postiz
- **Review queue**: All / Pending / Approved / Rejected filter
- **Killed legacy**: deleted 15 root HTMLs + 11 campaign-os/ HTMLs + 4 .bak files

## What still needs building (PRIORITY ORDER — keep in sync)
1. ✅ **Campaign Builder v2** — DONE (`d79945f`, 2026-07-27T20:45 SAST). Backend `campaign-os/_lib/campaign_planner.py` + 3 routes + full-plan UI on Campaigns section.
2. ✅ **Drag-and-drop calendar** — DONE (this tick). HTML5 drag-drop on calendar slots → drop on day = reschedule, drop on duplicate zone = create draft copy, color-coded by pillar/brand/platform, queue + campaign assets supported. Schedule sidecar endpoint writes runtime `scheduled-items.json`.
3. ✅ **Inline caption editor** — DONE (`03a4add`, 2026-07-27T21:xx SAST). Edit-in-place + save through `/api/assets/<assetId>` + regenerate single caption without page reload.
4. **Image generation pipeline** — `campaign-os/_lib/image_gen.py` with strict brand standards (colors, typography, platform format specs).
5. **Meme Lord v2** — meme historian + fit scoring + format knowledge + golf-aware humour.
6. **Marketing trends engine** — synthesizes golf-news + youtube + competitor + reddit into "what's working this week" + "what's new in golf" with action recs.
7. **Scheduling tool UI** — absorbed into completed drag-and-drop calendar.
8. **Meme Lord full UI** — meme encyclopedia + fit-score badges.

## Architecture (where things live)
```
campaign-os/
  app.py                       # Flask + routes (13 legacy + 4 intel = 17 routes)
  campaign-data.json           # canonical (Do NOT write directly)
  campaign-os.html             # THE SPA (75KB)
  _lib/
    intelligence.py            # 23 view functions (770+ LOC)
    visibility_guard.py        # existing — DO NOT TOUCH (Step 98/99 contract)
    __pycache__/
  tests/
    test_truth_collector.py
data/                          # 167 JSON files (April-May 2026 Phase 1/2 outputs)
```

## Quick-start for next session
```bash
# Server should already be running on 8765. If not:
cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard
source .venv/bin/activate
DATA_DIR=/tmp/campaign-os-data PORT=8765 python3 campaign-os/app.py

# Tunnel (for public URL):
cloudflared tunnel --url http://127.0.0.1:8765

# Verify all 23 views:
for r in morning_brief review_inbox calendar trends opportunities performance learning hooks memes billboards caption_studio postiz agents assets hooks_generate captions_generate ctas_generate headlines_generate explain reddit_outreach seo_assistant gbp_suggestions faq_generator trend_catcher; do
  curl -s -o /dev/null -w "%{http_code} /api/intel/$r\n" "http://127.0.0.1:8765/api/intel/$r"
done
```

## Hard rules
- DO NOT publish to Postiz (no API calls to Postiz)
- DO NOT touch `campaign-data.json` directly — use `/api/campaigns` POST or `/api/review/<id>` POST
- DO NOT touch `scripts/_lib/visibility-guard.js` or `campaign-os/_lib/visibility_guard.py`
- DO commit every phase; one commit per logical change
- DO write a status section at the end of every build session (append to this file)

## Roster of files to add
- `campaign-os/_lib/image_gen.py` — image generation pipeline (ComfyUI + brand standards)
- `campaign-os/_lib/meme_lord.py` — meme historian + fit scoring
- `campaign-os/_lib/campaign_planner.py` — full-plan generator
- `campaign-os/_lib/trends_engine.py` — marketing trends synthesizer
- Updates to `campaign-os/campaign-os.html` — drag-drop calendar, inline editor, image prompts panel
- Updates to `campaign-os/app.py` — schedule endpoint, image gen endpoint, plan endpoint

## Build principles
- A feature is **shipped** only when all three exist: backend endpoint (returns real data), front-end section (rendered in the SPA), UX (callable from the cockpit with ≤2 clicks).
- **UX bar**: every screen should feel like software someone would pay for. Fast, alive, minimal clicks, modern. If Christelle wouldn't open it on a Monday morning, it's not done.
- No raw JSON in user-facing UI — every card must render meaningful titles, pills, badges.
- Generators (hooks/captions/headlines/CTAs/images): always have an evergreen fallback so the user never sees an empty page.
- Image gen standards: every prompt must include brand colors (#0a0f1a dark / #34d399 green / #60a5fa blue), typography family, platform format (IG square/portrait/reel, GMB landscape), aspect ratio.
- Meme Lord must be a meme historian: know the format, know why it works, know how to adapt it for a Johannesburg golf brand, score fit 1-10.
- Marketing trends engine must be opinionated: not just "here are signals" but "here's what to do this week because of X".

## Agents you can call for help (delegate_task)
- Code-heavy multi-file work → coding subagent with full context + paths
- Visual / creative work (meme format encyclopedia, image-prompt libraries) → creative subagent
- Research (what's working in marketing this month, golf news synthesis) → research subagent
- Quality review (UX audit, "would I want to use this") → UX-review subagent

## Design tokens (use everywhere)
- Background: #0a0f1a (page), #101727 (card), #172033 (row), #1e2940 (hover)
- Border: #22304d, hover #2a3a5c
- Text: #e6ecf5 (primary), #a8b4cc (secondary), #6c7a96 (muted)
- Accent: #34d399 (primary green), #22c55e (hover), #60a5fa (blue), #a78bfa (purple), #fb923c (orange), #f87171 (red), #facc15 (yellow)
- Gradient: linear-gradient(135deg, #34d399 0%, #60a5fa 100%)
- Radius: 14px (card), 8px (small), 999px (pill)
- Font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif
- Header: 700 weight, -0.02em letter-spacing
- Pill: 10px font, uppercase, 0.04em letter-spacing, 3px 8px padding

## Test baseline (do not break)
- 433 passing / 0 failing / 3 skipped (live-API gated)
- Tests at: `tests/test_*.js`, `campaign-os/tests/test_truth_collector.py`
---

## Cron tick 2026-07-27T20:15 SAST (kickoff — pre-cron)

**Built**:
- Hourly cron job `da7bebf99c66` (12 ticks 22:00–10:00 SAST) for autonomous overnight build
- On-disk status handoff `CAMPAIGN_OS_STATUS.md` with priorities, design tokens, hard rules, agent-call guidance
- Committed working tree (37 files, +2,339 / −21,686) and pushed as `a60ef9a` to `origin/feat/asset-state-engine`
- Fresh public tunnel: `https://episodes-images-futures-coleman.trycloudflare.com` (live, 200)
- Re-stated cron prompt with the new "front-end + back-end + UX = shipped" bar + design tokens + delegate_task guidance

**Files added/modified**: `CAMPAIGN_OS_STATUS.md` (new + appended), staged-and-committed the entire previous-session SPA + intelligence module + 26 stale-UI deletions
**New routes**: none added this tick (all from previous session: 23 /api/intel/<view> + /api/search)
**New UI sections**: none added this tick (kickoff only)
**Tests added**: none this tick
**Commit**: `a60ef9a` + `git push -u origin feat/asset-state-engine` succeeded
**Verified live**: `https://episodes-images-futures-coleman.trycloudflare.com/` → 200; `/api/intel/morning_brief` → 200
**Next priority (PRIORITY 1)**: Campaign Builder v2 — full plan generator (goal/audience/pillars/hooks/calendar/image prompts/captions/KPIs). Backend at `campaign-os/_lib/campaign_planner.py`, frontend cards in `campaign-os.html` "Campaigns" section showing the generated plan for each campaign.
**Blockers**: none

---

## Cron tick 2026-07-27T20:45 SAST (kickoff + Campaign Builder v2)

**Built**: 
- **PRIORITY 1 — Campaign Builder v2** shipped end-to-end (backend + frontend + UX).
- Backend `campaign-os/_lib/campaign_planner.py` (23KB, 350+ LOC) — generates full marketing plans for any campaign.
- Routes: `GET /api/plan/portfolio`, `GET /api/plan/<campaign_id>`, `GET /api/plan/index`.
- Frontend: Campaigns section cards now have "📋 Full plan" button → expands full plan document with Goals, Persona, 5 Pillars (color-bordered), 15 hooks, 15 image prompts, 15 captions, 16-post 30-day calendar, KPIs, success criteria, day-7/14/30 winning criteria.
- Brand standards baked into every prompt: colors (#0a0f1a / #34d399 / #60a5fa), typography (Inter/SF Pro), platform format specs (IG 1080×1350 etc.), Golf Shack voice ("TrackMan numbers don't lie").
- Persona "The Curious JHB Club Golfer" baked into persona block for every campaign.

**Files added/modified**: 
- `campaign-os/_lib/campaign_planner.py` (NEW, 23KB)
- `campaign-os/app.py` (+3 routes)
- `campaign-os/campaign-os.html` (Campaigns section rewrite, ~120 LOC added)

**New routes**: `/api/plan/portfolio`, `/api/plan/<campaign_id>`, `/api/plan/index` — all 200
**New UI sections**: Full-plan expansion panel under each campaign card (Goals + Persona + 5 Pillars + Hook bank + Image prompt library + Caption library + 30-day calendar + KPIs + Success criteria)
**Tests added**: none this tick (planner is pure-function; will add unit tests in next tick if time permits)
**Commit**: `d79945f` pushed to `origin/feat/asset-state-engine`
**Verified live**: 
- `curl /api/plan/use-the-right-equipment-mq5l90bk` → 200, summary "5 content pillars · 15 hooks · 15 image prompts · 15 captions · 16 scheduled posts over 30 days"
- Browser vision screenshot confirmed full plan renders with Goals/Persona/5 pillars/hooks/image prompts/captions/16 calendar cards/48K reach KPI/200 follower KPI/5 success criteria/day-7/14/30 winning section.
- Public URL `https://episodes-images-futures-coleman.trycloudflare.com` still alive (tunnel not refreshed this tick)

**Next priority (PRIORITY 2)**: Drag-and-drop calendar. HTML5 drag-drop on calendar slots → drop on different day = reschedule, drop on side panel = duplicate, color-code by brand/pillar. Also: schedule endpoint `/api/schedule/<assetId>` that writes to `data/scheduled-items.json`.
**Blockers**: none

---

## Cron tick 2026-07-27T22:45 SAST (drag-and-drop calendar — PRIORITY 2 + sidecar writes)

**Built**:
- **Drag-and-drop calendar** shipped end-to-end (front + back + UX) — the calendar now reads as a real scheduling surface, not a feed.
- Backend (`campaign-os/app.py`):
  - `GET /api/schedule` — returns the publisher-compatible `scheduled-items.json` sidecar without mutating the source.
  - `POST /api/schedule/<asset_id>` — reschedule any campaign asset or publisher queue item; writes to runtime DATA_DIR, atomic `.tmp → os.replace`.
  - `POST /api/schedule/<asset_id>/duplicate` — creates a new campaign asset (deep copy via `copy.deepcopy`) OR a calendar-sidecar-only entry, with a new `assetId-copy-<uuid8>` so the calendar renders the copy immediately. Publish refs are cleared; approval resets to `draft`; the new ID never collides.
  - `DELETE /api/schedule/<asset_id>` — reverses a schedule without deleting the asset.
  - `_data_paths()` + runtime `DATA_DIR` resolution per call so tests can isolate. Helpers: `_now_iso`, `_normalise_schedule_datetime`, `_schedule_datetime_from_body`, `_read_publisher_queue`, `_campaign_target`, `_queue_target`, `_schedule_target`, `_manifest_entry`, `_upsert_schedule_entry`, `_schedule_response`.
- Intelligence (`campaign-os/_lib/intelligence.py`):
  - `calendar_view(days=14, start=None)` now merges campaign assets, the schedule sidecar, and the publisher queue. Queue items without explicit `publishDate` get synthetic per-day slots so the grid is never empty. `_calendar_color(pillar|brand|platform)` paints green/blue/orange/purple/yellow per pillar and per business. `_runtime_data_file()` prefers DATA_DIR over the bundled corpus so the sidecar wins.
  - Sidecar-only copies (queue duplicates without a campaign-asset home) render in the grid via a final pass that surfaces any orphan `scheduled[]` entries.
- SPA (`campaign-os/campaign-os.html`):
  - `.cal-grid` now uses `repeat(7, minmax(0, 1fr))` with `min-width:0` on day cells so 7 columns fit at 1280px without horizontal scroll.
  - Each slot is `draggable="true"`, has a brand-coloured left border, a name + meta row, and an explicit drag-only cursor.
  - Day cells are drop targets with a green-tint `drag-over` highlight; the calendar summary has a new colour-coded dot.
  - Added a violet duplicate drop zone below the grid with a "⧉ Drop here to duplicate" affordance.
  - Prev/Today/Next shifts the start date in real time via `S.calStart`; `data-cal-shift="0"` returns to today.
  - `calDragStart/Over/Leave/Drop/Duplicate` manage the drag state, prevent `dragover` default so drop actually fires, and round-trip through the new endpoints with toast feedback and re-render.
  - Same-day drops are a no-op with a friendly toast.
- Tests (`campaign-os/tests/test_calendar_schedule.py` — 6 new cases):
  - `GET /api/schedule` returns the publisher-shaped manifest.
  - `POST /api/schedule/asset-1` writes the sidecar, the calendar endpoint reflects the override on the new day.
  - Invalid ISO 8601 is rejected (400) with no file write; unknown asset/queue id is 404.
  - `POST /api/schedule/asset-1/duplicate` creates a new asset in `campaign-data.json` with cleared `publishingReferences`, draft approval, and a schedule entry in the sidecar.
  - Queue items can be rescheduled and duplicated without touching `campaign-data.json` (verifies the sidecar is the only write boundary).
  - Queue duplicates become visible on the calendar the next request.
- Hard rules respected: `campaign-data.json` writes go through `save_data()`; `visibility_guard.py` and `visibility-guard.js` untouched; no Postiz calls; no raw JSON in the UI.

**Files added/modified**:
- `campaign-os/app.py` — 5 new routes + scheduling helpers (was 920 LOC, now 958).
- `campaign-os/_lib/intelligence.py` — `calendar_view` rewrite + colour palette + sidecar orphan render (was 1014 LOC, now 1014).
- `campaign-os/campaign-os.html` — calendar CSS + drag/drop JS + duplicate zone (was 1268 LOC, now 1563).
- `campaign-os/tests/test_calendar_schedule.py` (new, 213 LOC, 6 cases).
- `CAMPAIGN_OS_STATUS.md` — drag-and-drop calendar marked ✅; scheduling-tool item collapsed into calendar.

**New routes** (all verified 200 against the live server):
- `GET  /api/schedule`
- `POST /api/schedule/<asset_id>`          (reschedule, 200)
- `POST /api/schedule/<asset_id>/duplicate` (copy, 201)
- `DELETE /api/schedule/<asset_id>`          (clear, 200)

**New UI sections**:
- Calendar grid with 14 day columns, brand-coloured slots, drag/drop reschedule, violet duplicate zone, prev/today/next week navigation, real-time colour-coded dot legend.
- 8 visible occurrences of `cal-duplicate-zone` in the SPA (CSS + HTML + drag handlers); 1 `draggable="true"` slot template.

**Tests added** (6 new + 67 existing = 73 passing / 0 failing):
- `test_calendar_schedule.py` exercises reschedule, duplicate, queue-only paths, validation, and the calendar override for the full happy + sad set.

**Commit**: `f674d91` (docs) + the code work landed in earlier commits on this branch; pushed to `origin/feat/asset-state-engine` at `f674d91f9faa393271d1503ac7e5913e7ed56a06`.

**Verified live**:
- `curl /api/health` → 200, server PID 81316.
- `curl /api/intel/calendar?days=2` → 200, 57 scheduled across 2 days; first slot carries `assetId`, `scheduledFor`, `source`, `color`, `brand`, `pillar`, `platform` — the colour-coded grid is fed by a real per-slot palette.
- `POST /api/schedule/<queue_item_id>` with `{"scheduledFor":"2026-08-06T09:00:00Z"}` → 200, response includes `source: "queue"` and the new `scheduledFor`; the sidecar is updated in `/tmp/campaign-os-data/scheduled-items.json`. `DELETE` clears it. No `campaign-data.json` mutation.
- Browser verification (`browser_navigate` + `browser_console`): `calDragStart`, `calDrop`, `calDuplicate`, `calDragOver`, `calDragEnd` all defined; 57 calendar slots render in the grid; 14 day cells expose `ondrop`; the duplicate zone is mounted; the SPA's `GET /` payload is 100 906 bytes and contains the new drag attributes.
- Vision screenshot of the live Calendar shows 7 columns at 1280px, no horizontal scroll, the violet duplicate zone, and the green "Rescheduled to 2026-07-28" toast after a programmatic drop simulation.
- `.venv/bin/python -m unittest discover -s campaign-os/tests` → `Ran 73 tests in 0.077s — OK`.

**Next priority (PRIORITY 4)**: Image generation pipeline — `campaign-os/_lib/image_gen.py` with strict brand standards (colors #0a0f1a / #34d399 / #60a5fa, typography, platform format specs).
**Blockers**: none.

## Cron tick 2026-08-03T10:56 UTC (visualizer HELP tooltips — 30 elements)

**Built**:
- **HELP tooltips on `/visualizer`** — 30 elements across the page now have `data-help` + `data-help-title` so a non-engineer can decode the visual-DNA engine, the Meta engagement signal, and the gpt-image-1 generator without leaving the page.
- **Same minimal IIFE port pattern** as meme-lab + cockpit (`campaign-os/visualizer.html` line ~337). HELP module is 47 lines of JS + 6 lines of CSS, identical shape to the other two pages. Each page is self-contained.
- **3 autoAttach hook points**: (1) `init()` runs autoAttach BEFORE dynamic content loads; (2) after `Promise.all([loadEngagement(), loadStats(), runGrid()])`; (3) `setInterval(autoAttach, 4000)` safety net for future dynamic injection.
- **Coverage map** (30): H1, search-status span, hero band + 2 inner lbls, 8 sidebar h3s, 4 stat tile lbls, main Generate card h3 + 3 form labels + Generate button, 6 modal h4s, 2 modal buttons.
- **Idempotent wiring**: `:not(.has-help-tip)` selector makes re-runs safe.
- No JS logic added beyond HELP module + 3 autoAttach call sites.

**Files added/modified**: `campaign-os/visualizer.html` (93 insertions / 30 deletions).
**New routes / UI sections / tests**: none this tick.
**Commit**: `5841fb1` pushed to `origin/feat/asset-state-engine`.

**Verified live**:
- 30/30 `[data-help]` elements wired on LIVE URL, 0 pageerrors
- 9 PNG screenshots at `/tmp/co-nightshift/walkthrough_visualizer_2026-08-03T125506_*.png` (full page, h1, sidebar score, sidebar brand recipe, tile total, main generate h3, generate button, discover, modal brand alignment)
- Modal tooltip pattern works end-to-end (open card → modal → h4 hovers → popover)

**Lane rules honored**: zero em-dashes in new copy, no publish/schedule, no fake stats, branch `feat/asset-state-engine`.

**Next priority**: sweep HELP onto remaining `.card-h h3` on Brand Directory detail panel (Palette, Archetypes, Typography, Voice, Headlines, CTA, Punctuation, Do-say-don't-say, Examples), or fix the `[object Object]` meme-lab voice-bible bug, or wire HELP on `login.html` / `meta-portal.html`.

**Blockers**: none.

## Cron tick 2026-08-03T10:56 UTC (visualizer HELP tooltips - 30 elements)

**Built**:
- **HELP tooltips on `/visualizer`** - 30 elements across the page now have `data-help` + `data-help-title` so a non-engineer can decode the visual-DNA engine, the Meta engagement signal, and the gpt-image-1 generator without leaving the page.
- **Same minimal IIFE port pattern** as meme-lab + cockpit (`campaign-os/visualizer.html` line ~337). HELP module is 47 lines of JS + 6 lines of CSS, identical shape to the other two pages.
- **3 autoAttach hook points**: (1) `init()` runs autoAttach BEFORE dynamic content loads; (2) after `Promise.all([loadEngagement(), loadStats(), runGrid()])`; (3) `setInterval(autoAttach, 4000)` safety net.
- **Coverage map** (30): H1, search-status span, hero band + 2 inner lbls, 8 sidebar h3s, 4 stat tile lbls, main Generate card h3 + 3 form labels + Generate button, 6 modal h4s, 2 modal buttons.
- No JS logic added beyond HELP module + 3 autoAttach call sites.

**Files added/modified**: `campaign-os/visualizer.html` (93 insertions / 30 deletions).
**New routes / UI sections / tests**: none this tick.
**Commit**: `5841fb1` pushed to `origin/feat/asset-state-engine`.

**Verified live**:
- 30/30 `[data-help]` elements wired on LIVE URL, 0 pageerrors
- 9 PNG screenshots at `/tmp/co-nightshift/walkthrough_visualizer_2026-08-03T125506_*.png` (full page, h1, sidebar score, sidebar brand recipe, tile total, main generate h3, generate button, discover, modal brand alignment)
- Modal tooltip pattern works end-to-end

**Lane rules honored**: zero em-dashes in new copy, no publish/schedule, no fake stats, branch `feat/asset-state-engine`.

**Next priority**: sweep HELP onto remaining `.card-h h3` on Brand Directory detail panel, or fix `[object Object]` meme-lab voice-bible bug, or wire HELP on `login.html` / `meta-portal.html`.

**Blockers**: none.

---

## Cron tick 2026-08-05T03:45Z (nightshift tick — wire 3 more card-h tooltips)

**Built**:
- **3 more static card-h tooltips wired** on `campaign-os/campaign-os.html`:
  - Line 977: Meme Lab "🎯 Top picks for ..." → `data-help-title="Top picks for this brand"` (329 chars body, 0 em-dashes)
  - Line 986: Meme Lab "📚 Meme historian · ..." → `data-help-title="Meme historian library"` (360 chars body, 0 em-dashes)
  - Line 3437: "👁️ Preview in brand font" (inside `renderBriefPreview()` template literal — h3 text was static so attr injection was safe) → `data-help-title="Preview in brand font"` (428 chars body, 0 em-dashes)
- All 3 auto-attached by existing `HELP.autoAttach()` 4s interval, picking up the established `cursor:help` + `border-bottom:dotted` affordance from commit `a904842`.

**Files added/modified**: `campaign-os/campaign-os.html` (3 insertions / 3 deletions).
**New routes / UI sections / tests**: none — pure attribute addition.

**Commit**: `fc2a551` pushed to `origin/feat/asset-state-engine`.

**Verified live**:
- `/api/health` 200
- 2/3 hover-verified on LIVE via Playwright (Top picks + Meme historian — popover state `hasShow=true, opacity=1`, innerHTML contains exact title + body)
- 1/3 HTML probe only (Preview in brand font — only renders at runtime when a user expands a campaign brief detail)
- 0 pageerrors, 0 em-dashes in new tooltips, 0 main branch touched

**Screenshots**:
- `/tmp/co-nightshift/walkthrough_2026-08-05T034304_live_top_picks_popover.png`
- `/tmp/co-nightshift/walkthrough_2026-08-05T034304_live_meme_historian_popover.png`

**Lane rules honored**: zero em-dashes in new copy, no publish/schedule, no fake stats, branch `feat/asset-state-engine`, no main branch.

**Next priority** (PRIORITY CARRY-OVER from last tick):
- Wire ~14 dynamic-template card-h h3s inside `renderBriefStyleGuide`, `renderBriefPreview`, `renderCampaignPlan`, and SEO Audit per-page detail (lines 7624-7764, 6870-6879). These need `${h3tip(...)}` builder calls — same pattern as Brand Directory detail panel (commit 7502-7560).
- OR fix the popover `top = r.bottom + window.scrollY + 6` pre-existing bug (line 1559) — popover is `position:fixed` so the `+ window.scrollY` is wrong, putting the popover below the visible viewport when triggered mid-screen. 1-line patch.

**Blockers**: none.

---

## Cron tick 2026-08-05T05:00Z (nightshift tick — popover position fix + flip-up clamp)

Picked up the **popover `top = r.bottom + window.scrollY + 6` carry-over** flagged in the 2026-08-05T03:45Z tick. Bug: `.help-pop{position:fixed}` but `showPop()` was adding `window.scrollX/scrollY`, placing the pop off-screen below the fold whenever the trigger was mid-page. Static screenshot proof from the prior tick showed popovers at y > 1800 in a 900-tall viewport.

**Files modified** (`commit 5b491cd`, pushed to `origin/feat/asset-state-engine`, +29/-7, 3 files):
- `campaign-os/campaign-os.html` (line 1555-1577): `showPop()` rewritten to use viewport coords; added vertical flip-up clamp (if `top + popR.height > vh - 8`, flip above trigger; fall back to shrink-to-fit).
- `campaign-os/visualizer.html` (line 349-365): same fix (visualizer DNA-metadata popover had the same bug).
- `campaign-os/cockpit-operational.html` (line 126-142): same fix (cockpit popover had the same bug).

**Verified live** (Playwright cookie-auth on Railway URL):
- Bundle probe (cache-busted `?cb=<ts>`): bundle_chars=392,683, `has_new_comment=true`, `has_old_bug=false`, `has_flip_up=true`, title `Campaign OS · Swing Shack`, 28 EXPLAINERS keys.
- Mid-page popover probe (LIVE, scrollY=1500, vh=900): trigger `🚀 Ready to publish` at y=313.65, popover rect.y=339.66, bottom=459.53, `inside_viewport=true`. `would_have_been_off_screen_old_bug=true` (old calc would have placed top at 1839.65, far past 900).
- Near-bottom flip-up probe (LOCAL, vh=400): trigger `⚠️ High-impact misses` at y=322, popover flipped to top=177.84/bottom=316.47. `flippedUp=true`, `inside_viewport=true`.
- 0 console errors, 0 pageerrors, `/api/health` ok. Horizontal clamp (`maxLeft`, `left < 8`) preserved.

**Screenshot (LIVE)**: `/tmp/co-nightshift/walkthrough_2026-08-05T050036_LIVE_popover_position.png`

**Lane rules honored**: zero em-dashes in new copy (`git diff | grep "—\|–"` = 0), no publish/schedule, no fake stats, branch `feat/asset-state-engine`, no main branch touched.

**Next priority**:
- Wire ~14 dynamic-template card-h h3s inside `renderBriefStyleGuide`, `renderBriefPreview`, `renderCampaignPlan`, and SEO Audit per-page detail. These need `${h3tip(...)}` builder calls (same pattern Brand Directory uses, commit range 7502-7560).
- OR a regression sweep: probe all 88 card-h h3 tooltips and confirm none break with the new viewport-relative math (especially h3s inside horizontal-scroll containers or `position:sticky` headers — those are rare on Campaign OS but worth a 5-min sweep).

**Blockers**: none.

---

## Cron tick 2026-08-05T07:39Z (nightshift tick — wire 6 h3 tooltips in brand-brief generator)

Picked up the **`renderBriefStyleGuide / renderBriefPreview` carry-over** flagged across the prior 3 ticks (fc2a551, db2d191, bb7b4df). The brand-brief generator surface — opened when a user clicks `🎨 Generate brief` on any brand card — had 6 card-h h3s without tooltips: the Generate brief header, plus Archetype / Palette + Typography / Voice anchor / Headlines bank / CTAs bank inside the brief result card. All 6 were plain `<h3>` text nodes inside a template-literal click handler.

**Fix (commit `0d3d3e2`, pushed to `origin/feat/asset-state-engine`, +17/-6, 1 file)**:
- `campaign-os/campaign-os.html` lines 7591-7605: defined a local `h3tip` builder inside the brief click handler (the Brand Directory detail panel's `h3tip` lives in the `[data-bd-view]` click handler and is not in scope here — see pitfall #49 about closure scope for nested forEach listeners).
- Added 6 new const-string help bodies (Generate brief / Arche / Palette + Type / Voice anchor / Brief Headlines / Brief CTAs). All under 400 chars, all plain-English, **0 em-dashes** (standing rule + lint_brand_copy pre-commit guard).
- Wrapped 6 plain `<h3>` tags in `${h3tip(...)}` calls (Generate brief header at line 7608, then 5 in the brief result card at lines 7660/7664/7667/7674/7677).
- Each new h3 carries `data-help` + `data-help-title` + `style="cursor:help;border-bottom:1px dotted var(--tx-2)"` so the existing HELP.autoAttach() + cursor/dotted affordance from commits 33faba4 / a904842 / 5b491cd picks it up for free.

**Verified live (Playwright cookie-auth on Railway URL)**:
- Bundle probe (cache-busted `?cb=1785908167`, 541,175 bytes): all 6 unique needles found in the served SPA.
- Login (cos_session via `/login` JSON POST, password `swing-shack-dev-2026`), navigate to `data-go="campaigns"`, wait for `[data-bd-brief]` (4 brand buttons rendered), click first brand's `🎨 Generate brief`, wait for `h3[data-help-title="Archetype"]`.
- Direct data-help attribute probe (the deterministic ground truth, not the singleton popover): **6/6 h3s found with `data-help-title` matching the expected title**, **6/6 `data-help` body strings start with the expected prefix** (Archetype = "The visual recipe the brief picked for this brand: canvas size (square IG, story..."), Palette + Type = "Live brand palette (hex per role)...", etc.).
- Affordance probe: **6/6 h3s have `cursor=help` + `border-bottom-style=dotted`** (CSS from a904842 carries over automatically).
- Popover fires on mouseenter for all 6 (popover singleton caches last-set content; data-help attribute is the ground truth).
- 0 PAGEERROR / 0 console errors.
- 6 per-h3 hover screenshots + 1 full-page screenshot at `/tmp/co-nightshift/walkthrough_2026-08-05T073917_BRIEF_H3_*.png`.

**Lane rules honored**: 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (`git diff | grep "—"` = 0), 0 JS logic added (only attribute + template-literal substitution), 0 publish.

**Next priority**:
- Still-to-wire card-h h3s: HashtagSEO "Why this score" + "Banned (filtered out)" (lines 1353/1354), Learning "🧠 Learning" (4240), Insights "📅 Weekly marketing report" (4270), campaign card `${esc(cname)}` (7452), brief list `${esc(label)}` (7498), brief detail `✅ ${bid} · ${tone} · ${surface}` (7647), pillar card `${esc(pil.label)}` (7759), assets section `✏️ Assets · click any field to edit` (7802), asset card `${esc(a.name || aid)}` (7830). 9 left, all in dynamic template-literal surfaces — same pattern as this tick.
- OR a regression sweep: probe all 88 card-h h3 tooltips and confirm none break with the new viewport-relative popover math (popover is singleton, but the visual position should still respect viewport for each h3).

**Blockers**: none.
