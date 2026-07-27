# Campaign OS — Status Handoff

**Branch:** `feat/asset-state-engine`
**HEAD:** `3b31f24` (just pushed)
**Live URL:** `https://episodes-images-futures-coleman.trycloudflare.com`
| **Tests:** 112/112 pass (`cd campaign-os && source ../.venv/bin/activate && python3 -m unittest discover -s tests`)

---

## What just shipped (this turn)

**Inline Asset Editor** — backend `PATCH /api/assets/<id>` + `GET /api/assets/<id>/history` + new "✏️ Assets — click any field to edit" section inside every expanded campaign plan. 36 editable cards per campaign for "Use the Right Equipment" alone. ⌘+Enter saves, Esc reverts, History button expands audit trail.

**Also shipped:** `_data_paths()` per-call resolution so tests can isolate DATA_DIR cleanly.

## What's done across all turns

- ✅ Morning Brief (alive homepage: 4 stat cards, hot ticker, do-first/needs-review/ready-to-publish/misses/SEO/post-today)
- ✅ 23 intelligence views (`/api/intel/<view>`) — campaign-data.json + 167 data files aggregated
- ✅ Universal search (`/api/search?q=`)
- ✅ Single SPA (`campaign-os.html`, 100KB+, sidebar with 21 nav entries across 5 sections)
- ✅ Campaign Builder v2 — full plans: goals/persona/5 weighted pillars/15 hooks/15 image prompts/15 captions/16-post 30-day calendar/KPIs/success criteria/day-7/14/30 winning picture
- ✅ Drag-and-drop calendar (HTML5 DnD on slots, color-coded by pillar, `/api/schedule/<assetId>` POST/DELETE, duplicate-zone, queue-item scheduling)
- ✅ Inline asset editor
- ✅ Caption Studio, Headlines, CTAs generators (composed from hook bank + base caption + CTA pill)
- ✅ **Meme Lord v2** (THIS TURN) — meme historian: 75 curated memes across eras with brand-fit scoring, top-picks recommender, caption-draft generator (3 flavours), filter bar (voice/pillar/platform/era/still-works/search), modal with why-it-works + format-hint + fit-seeds + re-roll on different seed.
- ✅ 112 passing tests (was 73 before — +39 new for Meme Lord v2)

## Priorities for next cron iteration

4. **Meme Lord v2** — turn into a meme historian. Add a `meme_knowledge.json` data file with the ~200 most viral memes from the last decade (Distracted Boyfriend, Drake, Woman Yelling at Cat, etc.) + format taxonomy + brand-fit scoring. Front-end: every meme card has its era, peak year, why-it-works, brand-fit slider.
5. **Trend Catcher v2** — split into 3 sources: (a) marketing industry signals (HubSpot, Marketing Brew, AdWeek via RSS if available, else curated seed data); (b) golf news (PGA Tour, LPGA, DP World Tour, equipment releases — via RSS if available); (c) competitor moves (TrackMan, Foresight, Toptracer — monitor their social via search). Each signal gets a relevance score + suggested response.
6. **Image generation pipeline** — needs API creds to test live. Build the infrastructure now: `asset-image-spec.json` with brand-style rules (color palette, typography, model hint per pillar, aspect ratios per platform); `/api/intel/generate_image` that returns the structured prompt spec ready for any provider (Ideogram/DALL-E/MJ). When creds arrive, swap the provider in 1 file.
7. **Caption Studio v2** — add voice/tone picker (Swing Shack voice vs Stick voice vs Bag Drop voice — use the meme-voice-bible files). Multiple voices = different base captions.
8. **Right-rail "Today" panel** — make Morning Brief feel like a Bloomberg terminal: live timestamps, pulse animations on new items, dismissible cards.
9. **Dark mode / theme tokens** — current dark theme is good; ensure consistency across all surfaces.
10. **Publish Dashboard** — wire up the actual Postiz publish path through the SPA: list, schedule, send. (Needs careful gating per the no-publish-during-rest-mode rule.)

## Hard rules (do not violate)

- DO NOT publish to social, schedule in Postiz, or enable any GMB cron during Christelle's rest mode.
- DO NOT push to GitHub unless explicitly asked or already in scope of current feature work.
- DO NOT call MiniMax-fallback for critic-critical tasks.
- DO NOT modify the canonical `campaign-data.json` outside of test fixtures.
- DO verify every endpoint with a real `curl` or browser before declaring done.
- DO update this file at the end of every build cycle.
- DO commit at the start AND end of each cron iteration if anything changed.
- DO `git push origin feat/asset-state-engine` after committing.
- DO keep responses concise (no filler, no summary of "I read this and that").
- DO call specialists via delegate_task when their expertise beats yours (e.g. Meme Lord work → ask Copywriter for tone; image prompts → ask Copywriter for punch).

## Where to find things

```
campaign-os/
├── app.py                              # Flask backend, ~920 LOC, all routes
├── campaign-os.html                    # Single SPA, ~1500 LOC, all front-end
├── campaign-data.json                  # CANONICAL — do not modify outside tests
├── _lib/
│   ├── intelligence.py                 # 23 intelligence views, ~1010 LOC
│   └── campaign_planner.py             # Campaign Builder v2, 23KB
├── tests/
│   ├── __init__.py
│   ├── test_calendar_schedule.py       # 6 tests, drag-drop + sidecar
│   ├── test_inline_asset_edit.py       # 11 tests, PATCH /api/assets
│   ├── test_truth_collector.py         # (legacy, still passes)
│   └── ...                             # (legacy test files preserved)
├── tests/__init__.py
└── BUILD_STATUS.md                     # (legacy, may not exist)
```

## How to run a build cycle

```bash
# 1. Read this file (CAMPAIGN_OS_STATUS.md) at start
# 2. Verify server alive:
curl -s http://127.0.0.1:8765/api/health

# 3. Verify tests:
cd campaign-os && source ../.venv/bin/activate && python3 -m unittest discover -s tests

# 4. Build next priority end-to-end (front + back + UX + tests)
# 5. Commit + push:
git add campaign-os/ && git commit -m "feat: <what>" && git push origin feat/asset-state-engine

# 6. Verify live URL:
curl -sI https://episodes-images-futures-coleman.trycloudflare.com | head -1

# 7. Update this status file (the next cron reads it)
```

## Cron tick 5 — 2026-07-28 00:00 SAST
Built: Trend Catcher v2 — curated marketing-industry, golf-news, and competitor signal radar with relevance scoring, filters, and suggested responses.
Files: data/trend_signals_v2.json; campaign-os/app.py; campaign-os/campaign-os.html; campaign-os/tests/test_trends_v2.py
Tests: 114/114 pass (+2 Trend Catcher tests); endpoint route fix committed and pushed.
Next: Image generation pipeline (priority 6)## Recent commits

```
3b31f24  feat(campaign-os): Meme Lord v2 — meme historian + brand-fit recommender
2fb0b7b  docs: tick-3 cron status block — drag-and-drop calendar
f674d91  docs: tick-3 — mark drag-and-drop calendar shipped
f8acd62  docs: Campaign OS status handoff for next cron iteration
03a4add  feat: Campaign OS — inline asset editor + dynamic DATA_DIR
```

## Known issues / blockers

- **Railway CLI unauthorized** → no permanent public URL. Cloudflare ephemeral tunnel is the current mechanism.
- **No image-generation API creds** → building prompt infrastructure only; full integration when creds arrive.
- **Cloudflare tunnel expires when cloudflared exits** → if URL is down on next cron tick, kill+restart `cloudflared tunnel --url http://127.0.0.1:8765` and grep the new URL from `/tmp/cloudflared.log`.
- **Pyright false positives** on `_sys.path.insert` and runtime path mutations — ignore; runtime is correct.
- **3 phase_tdz live-API tests still skipped** (pre-existing, gated behind `LIVE_NETWORK_TESTS=1`).

## Cron tick 6 — 2026-07-28 01:17 SAST
Built: Image generation pipeline — brand image specification plus provider-ready structured prompt generation for Ideogram, DALL-E, Midjourney, and Stable Diffusion; single-SPA Image Gen controls and copy UX.
Files: data/asset-image-spec.json; campaign-os/_lib/intelligence.py; campaign-os/app.py; campaign-os/campaign-os.html; campaign-os/tests/test_image_generation.py; campaign-os/tests/test_inline_asset_edit.py
Tests: 152/152 pass (+38 image-generation tests); GET/POST endpoint verified by Flask tests and live curl; Image Gen SPA verified in browser.
Next: Caption Studio v2 (priority 7)

---

## Cron tick 4 — 2026-07-27 21:10 SAST

**Built:** Meme Lord v2 — meme historian + brand-fit recommender

**Files:**
- `data/meme_knowledge.json` — 75 curated memes across 3 eras (classic/mid/recent) with format/mechanism taxonomy, voice_bible (swing-shack/stick/bag-drop), era+fatigue+brand-fit scoring seeds per meme
- `campaign-os/app.py` — added `_load_meme_knowledge()`, `_score_meme_brand_fit()`, `_filter_memes()`, plus 3 new endpoints:
  - `GET /api/intel/meme_knowledge` (filters: era, format, mechanism, voice, pillar, platform, only_still_works, search; sort: brand_fit/peak_year/name)
  - `GET /api/intel/meme_recommend` (top-N for voice+pillar+platform with alternates)
  - `POST /api/intel/meme_apply` (returns 3 caption flavours + brand-fit + voice rules; supports user hook + pick_seed_index for re-rolls)
- `campaign-os/campaign-os.html` — full Meme Lord section rewrite: filter bar, top-picks grid (with brand-fit badge + era+fatigue chips + fit-seeds details), historian library (sortable rows), modal with full meme detail and "Generate caption" flow (copy-to-clipboard + re-roll on different fit-seed)
- `campaign-os/tests/test_meme_lord_v2.py` — 39 new tests covering envelope shape, data shape, all 8 filter dimensions, brand-fit scoring with voice/pillar permutations, apply endpoint edge cases (400/404/error envelopes), caption flavour generation, fit-seed wrapping, voice_bible rules

**Tests:** 112/112 pass (was 73; +39 new)
**Verified via:** curl `/api/intel/meme_knowledge?limit=2`, `/api/intel/meme_recommend?voice=stick&pillar=club-fitting&platform=tiktok`, `/api/intel/meme_apply` (POST), `https://episodes-images-futures-coleman.trycloudflare.com/api/health` returns 200
**Server:** restarted on PID 83959; Cloudflare tunnel still up

**Next priority:** Trend Catcher v2 (priority 5) — split signals into 3 sources (marketing industry / golf news / competitors), add relevance scoring + suggested response for each signal.