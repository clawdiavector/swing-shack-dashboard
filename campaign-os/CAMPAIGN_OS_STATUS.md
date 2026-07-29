# Campaign OS — Status Handoff

**Branch:** `feat/asset-state-engine`
**HEAD:** `a20c327` (just pushed)
**Live URL:** `https://episodes-images-futures-coleman.trycloudflare.com`
| **Tests:** 233/233 pass (`cd campaign-os && source ../.venv/bin/activate && python3 -m unittest discover -s tests`)

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
- ✅ **Theme tokens + light/dark switcher** — two-tier CSS token system (`:root` aliases + `[data-theme]` overrides) with full dark + light themes, `prefers-color-scheme` auto-mode, topbar switcher pill (Dark/Light/Auto), `localStorage` persistence, server-side `GET/POST /api/intel/theme` + `GET /api/intel/tokens` design-system manifest. Every raw hex removed from CSS — all colors flow through semantic tokens (`--bg`, `--tx`, `--ac`, `--scrim`, `--pill-on`, etc.); meme era/fatigue/brand-fit palette uses `color-mix()` so it auto-themes.
- ✅ 233 passing tests (was 73 baseline; +160 across all turns)

## Cron tick 12 — 2026-07-28 08:15 SAST

**Built:** SEO Audit Detail (deep-dive on seo-audit.json + landing-page-fixes.json) — rest-mode-safe intelligence view that previous cron (tick 11) had built but never committed. Hit a TDZ runtime bug in the SPA where `const SA_STATE`/`SA_TYPE_LABELS` were unreachable from `renderSeoAudit`'s hoisted function — fixed by converting to `var` so listener handlers fire cleanly during script eval.

**Files:**
- `data/seo-audit.json` — 16 findings across 4 pages (Homepage, Membership, Coaching, Club Fitting), 8 high / 4 medium / 4 low severity, with per-finding type/message/severity/priority/action
- `data/landing-page-fixes.json` — 7 high-impact landing-page fixes (pricing_clarity, cta_weak, intent_mismatch, friction, trust_gap, faq_missing, awareness_gap) each with fix_id/evidence/expected_outcome/revenue_impact
- `campaign-os/app.py` — 3 new endpoints:
  - `GET /api/intel/seo_audit_detail?page&type&severity&only_fixable` — health score (0-100), band (healthy/needs_attention/poor/critical), by_page (with normalised findings + per-page score), by_severity, by_type, recommendations, top_priority_actions, landing_fixes summary, valid_pages/severities/types, filters_applied
  - `POST /api/intel/seo_audit_fix_draft` — generates ready-to-paste fix snippets for 4 finding types (missing_meta_description 110-160 chars, missing_h1 ≤70 chars, title_too_short 50-60 chars, missing_faq 3-5 questions), with custom_keyword override and character-count validation
  - `GET /api/intel/seo_audit_index` — manifest with action_map, valid filter values, landing_fixes summary
- `campaign-os/campaign-os.html` — new `#sec-seo-audit` section + nav entry `📋 SEO Audit`: health-score card + filter bar + per-page findings + top-priority-actions sidebar + all-recommendations + landing-page-fixes + fix-draft modal. **TDZ fix**: `const SA_STATE`/`SA_TYPE_LABELS` → `var`
- `campaign-os/tests/test_seo_audit_detail.py` — 60 new tests across 7 classes (SeoScoreTests, SeoGroupByPageTests, SeoFixTemplateTests, SeoAuditDetailApiTests, SeoFixDraftApiTests, SeoAuditIndexApiTests, BundledFallbackTests)

**Tests:** 293/293 pass (was 233; +60 SEO Audit Detail tests); zero baseline regressions. Verified live via curl + browser.

**Next priority:** Reddit Reply Drafter (rest-mode-safe) or GBP Post Drafter. Or revisit existing renderer stubs (`renderBillboards`, `renderHeadlines`, `renderCTAs`) to bring them up to v2 polish. Publish Dashboard (priority 10) still gated behind rest-mode.

---

## Cron tick 11 — 2026-07-28 06:00 SAST

**Built:** Hashtags & SEO Pack engine (priority 11, rest-mode-safe) — pure-read intelligence for curated hashtag sets + on-page SEO scaffolding. Avoided Publish Dashboard (priority 10) because it's blocked during Christelle's rest-mode and would otherwise gate the next cron. Hashtag/SEO Pack ships the same operational value (publish-pack ready, brand-fit scored) with zero social/Postiz surface.

**Files:**
- `data/hashtag_seo_pack.json` — 78 tags across 4 pillars × 3 voices × 5 platforms, trending signals (7), banned tags (4), full SEO templates (titles / meta / h1 / slug rules / alt-text rules / schema types / og descriptions), brand keyword bank
- `campaign-os/app.py` — 4 new endpoints + 2 helpers (`_build_hashtag_set`, `_score_hashtag_set`, `_render_seo_pack`, `_normalise_tag`):
  - `GET /api/intel/hashtags?pillar&voice&platform&count&include_trending&search&banned_only` — curated hashtag set with banned filter, trending filter, search filter, platform-max cap, GMB→empty
  - `GET /api/intel/seo_pack?pillar&voice&platform&custom_keyword` — full SEO pack with scoring
  - `POST /api/intel/seo_pack` — JSON-body alias
  - `GET /api/intel/seo_index` — manifest for SPA picker
- `campaign-os/campaign-os.html` — new `#sec-hashtagseo` section + nav entry `#️⃣ Hashtags & SEO`: pillar/voice/platform/count controls, hashtag pills (click to copy), score badges, banned-filter display, platform tips card, full SEO pack card (title/h1/meta/slug/alt/og/schema/keywords), trending signals, brand keywords; auto-regenerates on control change
- `campaign-os/tests/test_hashtag_seo.py` — 50 new tests across 4 classes:
  - `HashtagNormalisationTests` (6): leading-hash, lowercase, dedupe-hash, whitespace, empty/non-string rejection
  - `HashtagApiTests` (23): envelope shape, all-pillar/voice/platform permutations, banned filter, banned-only diagnostic, GMB→empty, count cap, platform-max cap, search filter, include_trending toggle, score in-range, by_category keys, brand tag presence, error envelopes (400 for invalid pillar/voice/platform/count, missing params)
  - `SeoPackApiTests` (16): envelope shape (GET + POST), pack keys, page_title ≤70, meta_description 110..160, slug well-formed, alt-text sized, schema type per pillar, score in-range, score ≥80 for known pillars, custom_keyword override, secondary keywords, primary-keyword-in-meta
  - `SeoIndexApiTests` (5): envelope shape, pillar/voice/platform lists, stats keys
  - `BundledFallbackTests` (1): engine still serves requests when DATA_DIR is empty

**Tests:** 233/233 pass (was 183; **+50 hashtag/SEO tests**); zero baseline regressions. Verified live: `curl /api/intel/hashtags?pillar=education&voice=swing-shack&platform=instagram`, `curl /api/intel/seo_pack?pillar=club-fitting&voice=stick`, `curl /api/intel/seo_index`, all return 200. Tunnel still alive.

**Next priority:** Publish Dashboard (priority 10) — still blocked by rest-mode. Next rest-mode-safe candidates: SEO Audit Detail (deep-dive on seo-audit.json), GBP Post Drafter, Reddit Reply Drafter, Calendar Heatmap (read-only). Or revisit existing renderer stubs (`renderBillboards`, `renderHeadlines`, `renderCTAs`) to bring them up to the same polish as Meme Lord / Caption Studio.


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
│   ├── test_image_generation.py        # 38 tests, prompt pipeline
│   ├── test_meme_lord_v2.py            # 39 tests, meme historian
│   ├── test_today_panel.py             # 3 tests, right-rail Today
│   ├── test_trends_v2.py               # 2 tests, Trend Catcher v2
│   ├── test_theme_tokens.py            # 28 tests, dark/light/system
│   ├── test_hashtag_seo.py             # 50 tests, hashtag + SEO pack
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

## Cron tick 8 — 2026-07-28 03:05 SAST
Built: Right-rail Today panel — Bloomberg-style live cards in Morning Brief with dismissable per-card action, live UTC timestamp header, 30-second pulse refresh, colour-coded by lane (action/review/publish/post).
Files: campaign-os/app.py; campaign-os/campaign-os.html; campaign-os/tests/test_today_panel.py
Tests: 155/155 pass (was 152; +3 today panel); endpoints verified via live curl + tunnel.
Next: Dark mode / theme tokens (priority 9)

## Cron tick 9 — 2026-07-28 04:08 SAST

**Built:** Dark mode / theme tokens — two-tier CSS token system (`:root` aliases + `[data-theme]` overrides) with full dark + light themes, auto/system mode following `prefers-color-scheme`, in-app theme switcher, and a `/api/intel/tokens` design-system manifest endpoint.

**Files:**
- `campaign-os/app.py` — added `_load_theme_state()` / `_save_theme_state()` (DATA_DIR-isolated, history-bounded to 20 transitions, no-op de-dup) plus 3 new endpoints:
  - `GET /api/intel/theme` — current theme + supported values + transition history
  - `POST /api/intel/theme` — persist `dark`/`light`/`system` (400 on bad value, with type-safe validation for non-string bodies)
  - `GET /api/intel/tokens` — 20-token design-system manifest (name, kind, dark value, light value, purpose) for QA / extension
  - `_data_paths()` extended with `theme_file` → `theme-preferences.json`
- `campaign-os/campaign-os.html` — full token refactor:
  - 33 raw hex colors removed from CSS — every color now flows through a token (e.g. `--slot-hover`, `--today-amber`, `--pill-on`, `--modal-scrim`, `--scrim`, `--badge-voice-tint`, etc.)
  - 6 raw rgba tints replaced with semantic tokens (`--rail-accent`, `--strip-tint-a/b`, etc.)
  - `[data-theme="dark"]` (default), `[data-theme="light"]`, and `@media (prefers-color-scheme: light)` auto-mode blocks all share the same alias names
  - Semantic meme palette (`era-classic/mid/recent/current`, `fatigue-low/medium/high`, `bf-hi/md/lo/zero`) refactored from inline hex to `color-mix(in srgb, var(--m-classic) NN%, transparent)` — auto-themed
  - Calendar slot JS dropped hardcoded `'#34d399'` fallback; defaults now inherit `var(--ac)` from CSS
  - Voice-chip inline rgbas (`rgba(52,211,153,.12/.15)`) replaced with `var(--badge-voice-tint/-2)` tokens
  - `<meta name="theme-color">` now has an `id` so JS can update it on theme change (mobile Chrome address bar tint)
  - Theme switcher pill rendered in the topbar with three buttons (🌙 Dark / ☀️ Light / ⚙️ Auto); `initTheme()` runs at boot, reads/writes `localStorage['swing-shack:theme']`, sets `data-theme` attribute, updates meta tag, persists server-side via POST, and listens to `matchMedia('(prefers-color-scheme: light)')` change events when on Auto
- `campaign-os/tests/test_theme_tokens.py` — 28 new tests across 3 classes:
  - `ThemeApiTests` (12): GET default envelope + history bounding, POST persistence + transitions, 400 for invalid values (including non-string bodies), no-op dedup, file-on-disk verification, corruption recovery
  - `TokensApiTests` (5): envelope, token shape, core-palette coverage, dark≠light contrast sanity, hex format validation
  - `ThemeCssStructureTests` (11): data-theme block presence, prefers-color-scheme media query, theme switcher DOM, localStorage key, meta theme-color id, **no raw hex outside theme blocks** (enforced), no raw hex literals in JS inline styles, color-mix used for semantic palette, switcher position in topbar

**Tests:** 183/183 pass (was 155; **+28 theme tests**); zero baseline regressions. Verified live: `curl /api/intel/theme`, POST light/system/invalid, GET tokens, browser screenshots of both themes in Morning Brief + Meme Lord sections (era chips, brand-fit badges, fatigue chips all theme-aware).

**Next priority:** Publish Dashboard (priority 10) — wire up the actual Postiz publish path through the SPA. Needs careful gating per the no-publish-during-rest-mode rule (Christelle on holiday; UI can show the dashboard but the action buttons must be disabled until rest-mode is lifted).

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