
## 2026-08-09T14:08Z — fix(campaign-os): Brief "What's new" title no longer leaks literal [object Object]

**Done:** Pre-pick sweep (`scripts/sweep.py`-style Playwright walk over 21 sections) caught the Morning Brief rendering literal `[object Object]` text in production — in the GBP-location regression-test row of the "What's new" card. The bug it describes is already fixed in the codebase; the *description* of the bug quoted the broken token verbatim (`"GBP profile 'Location [object Object]' becomes city, region · country"`), and the SPA rendered that title as-is. Result: Christelle opens Campaign OS and reads `[object Object]` in the morning — looks like a live regression.

Rewrote the title to describe the fix without quoting the bug token:
`GBP profile header reads 'city, region · country' (no more raw-object leak)`.
Body copy preserved (still mentions Sandton / Gauteng / South Africa) so the technical content is intact.

Added `test_v2026_08_09_whats_new_no_object_object.py`: static-regex parse of the `WHATS_NEW` list literal in `app.py`, asserts no entry contains `[object Object]` (case-insensitive). Future hand-edits that reintroduce the leak will fail loudly in `unittest discover`.

**Commit:** `addde62` on `feat/asset-state-engine`, 2 files (`campaign-os/app.py` +1/-1, `campaign-os/tests/test_v2026_08_09_whats_new_no_object_object.py` NEW +67/-0), pushed. Railway auto-deployed in ~90s.

**Verified (Playwright LIVE, cookie auth, Railway URL):**
- Pre-fix: `BRIEF [object Object] hits: 1` in `.wn-title` (`GBP profile 'Location [object Object]' becomes city, region · country`).
- Post-fix: `hits: 0`. New title rendered verbatim in `.wn-title`: `GBP profile header reads 'city, region · country' (no more raw-object leak) · 2026-08-08 00:10 UTC`. Other 12 rows unchanged. `/api/health` 200. 0 PAGEERROR. 0 console errors.
- 113/113 tests pass (`unittest discover -s campaign-os/tests -p test_v2026_*.py`).

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_20260809T135708Z_brief_fixed.png` — full-page Brief (Welcome modal visible at top, but the What's new list below the modal clearly shows the 13 rows with the GBP row now clean).
- `/tmp/co-nightshift/walkthrough_20260809T135733Z_whats_new_zoom.png` — zoomed What's new card, GBP row third.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (`git diff | grep "—"` = 0), 0 JS logic added (literal-text substitution only), 0 schema change, 0 helper removed, 1 new regression test added.

**Learned:** The WHATS_NEW list is hand-authored — it can rot just like generated copy does. The original GBP regression-test title was a self-aware joke ("here's what the broken text used to look like") that aged into a real UX bug the moment the fix shipped. Lesson: titles/bodies that *describe* bugs should describe the fix, not quote the broken token. The new test enforces that going forward.

**Next pick:** Insights tab still has the carry-over from 2026-08-06T01:45Z — `renderInsights()` clones Performance widgets but the data layer doesn't actually differentiate (only the explainer does). Real lane: add an Insights-only widget (week-over-week deltas, recommended-next-brief card) so the "Why lens / What lens" promise lands. Or add the visualizer `data-help-title` sweep the prior 2026-08-05T18:30Z tick flagged (modal h3s: Meme modal, GMB edit/new, Asset not found, Edit caption, Generic modal).

**Asks:** None.

**Done:** Insights tab was rendering two orphaned collapsed `<details>` boxes ("How to read performance data" + "How to read Google Analytics (GA4)") right under the H2 — they looked like broken empty accordions because the v2 lens banner ("🔍 How to read this view") below them was already a richer superseding explanation. Root cause: `go()`'s post-loadSection `HELP.section('insights', 'ga4')` mount dated from when `renderInsights` cloned sec-performance into sec-insights and needed the cloned perf explainer swapped out for the Insights-specific one. Since the Insights v2 rewrite, `renderInsightsV2()` is the sole renderer (old clone-based code preserved as a reference but never runs) and mounts its own lens banner; the post-mount just adds dead duplicate boxes. One-line guard: `if(realSec === 'insights') return;` inside the post-loadSection `.then(...)` block in `go()`.

**Commit:** `77ee6b9` on `feat/asset-state-engine`, 1 file (`campaign-os/campaign-os.html`), +9/-0 (all comment + the one-line guard), pushed.

**Verified (Playwright LIVE, cookie auth, Railway URL):**
- Pre-fix: `#sec-insights` had 2 `<details.help-collapsible.help-section-explainer>` summary boxes stacked under the H2.
- Post-fix: 0 such panels. v2 lens banner `.insights-lens-ctx` still present (1 instance). H2 unchanged. 0 PAGEERROR. 0 console errors.
- Regression sweep (other sections still get their explainers): Performance → 2 summaries (perf + GA4). Trends → 2 summaries (trend catcher + Meta).
- Insights content below the banner: 2 "What happened" headline cards + 8 Top IG Posts rows + 5 Top pages rows + ad-correlation block — all unchanged.

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-09T014300Z_insights_FIXED.png` — clean Insights tab (no orphan accordions, lens banner in place)

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (0 in the new comment block — used `//` line comments only), 0 NEW JS logic (single `if(...) return;` early-return guard), 0 schema change, 0 helper removed (post-mount still runs for every other section).

**Learned:** The `go()` post-loadSection `HELP.section` re-mount was originally paired with a `renderInsights` clone-from-performance that no longer runs. The companion comments at lines 4521-4528 describe the old "swap the cloned perf explainer for the Insights-specific one" intent — that intent is now stale because `renderInsightsV2()` never clones, it renders fresh content with its own banner. The pre-mount (`mountSec = 'performance'` for insights) is harmless because sec-performance isn't the active view, but worth a follow-up to remove if we confirm no other consumer depends on sec-performance having an explainer mounted while insights is active. The orphan-accordion pattern is general — any time a renderer fully replaces section content, post-mount explainer helpers that were paired with the old renderer's clone pattern become silent UI rot.

**Next pick:** Top IG Posts show `no img` placeholders on every row — `thumbnail_url` field on `/api/insights/top-instagram-posts` is either missing or 404ing on Railway (the live screenshot shows 8 "no img" gray boxes with red engagement rates). Visualizer thumbnails use the `thumbnail_data_url` pattern; the Insights API probably needs the same fix on the server side (`/api/insights/top-instagram-posts` in `campaign-os/app.py` around line 4057-4074). Could be a single missing field-extraction line. Then the empty 3rd "What happened" grid slot — the headlines grid is `col-4 col-4 col-4` but only 2 cards fill it when SEO keyword data isn't wired; layout would benefit from `col-6 col-6` when only 2 cards, or a "no SEO data" placeholder in the 3rd slot.

**Asks:** None.

## 2026-08-06T06:16Z — fix(campaign-os): ship thumbnail_data_url on /discover + use it in renderImageCard (eliminates the last visualizer 404 surface)

**Done:** Two-part fix that closes the last residual 404 on the Visualizer page (the one `takomo.png` outlier identified in last tick's report was the only thing left after the visualizer.html thumbnail_data_url patch).

1. **Server (app.py):** `/api/visual-library/<brand>/discover` was reading metadata-only `all-elements.json` and emitting `image_url: /api/visual-library/<brand>/image/<fn>.jpg` (a JSON DNA endpoint) as the only image source. Mirrored the `/api/visual-library/<brand>/images` pattern: added `_resolve_dna` (path fallback for Railway where index stores bogus absolute local paths) + per-result DNA read + `thumbnail_b64` → `data:image/jpeg;base64,...` extraction. Docstring updated to reflect the new `thumbnail_data_url` field.
2. **Client (visualizer.html line 557):** The `runDiscover` flow normalizes API results to `{filename, url, thumbnail_data_url, ...}` and renders via `renderImageCard`. That renderer had a stale `<img src=${img.url}>` hardcode — never the data-URI preference. After the server started shipping `thumbnail_data_url`, the state.images[i].thumbnail_data_url was set but the rendered src still pointed at `/api/visual-library/<brand>/image/<fn>.jpg`. Mirrored the `loadImages` render at line 681: `imgSrc = img.thumbnail_data_url || img.url`.

**Commits (both on feat/asset-state-engine, pushed, Railway auto-deployed):**
- `9174d60` — server: discover endpoint ships `thumbnail_data_url`
- `164479e` — client: renderImageCard prefers `thumbnail_data_url`

**Verified (Playwright LIVE, cookie auth, Railway URL):**
- **Default grid:** 122 cards rendered, **121/122 use `data:image/jpeg;base64,...` src, naturalWidth>0**. 1 missing = `takomo` (its DNA file legitimately has no `thumbnail_b64` field — data condition, not code).
- **Discover grid** (after clicking a color filter pill, 42 results returned): **42/42 use `data:image/jpeg;base64,...` src, naturalWidth>0** (was 0/42 before the client fix).
- **Modal** (click first discover card): `modal-img.src = "data:image/jpeg;base64,..."`, `naturalWidth: 540`.
- **HTTP 404s on /brand-images/** during discover flow: 1 (just the pre-existing `takomo.png` data condition).
- **PAGEERROR:** 0. **Console errors:** 2 (1 is the takomo.png 404, 1 is the pre-existing meta redirect to `?brand=swing-shack` that was there last tick).
- **Regression:** `/`, `/visualizer`, `/meme-lab` all 200. Sibling `/api/visual-library/<brand>/images`, `/recipe`, `/stats`, `/brands` all 200.

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_discover_01_visualizer_default.png` — LIVE default grid (121 data URIs)
- `/tmp/co-nightshift/walkthrough_discover_02_after_filter.png` — LIVE after clicking a blue-color discover pill (42 data URIs)
- `/tmp/co-nightshift/walkthrough_discover_03_modal.png` — LIVE discover-result modal

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 em-dashes added, 0 NEW JS logic beyond a single `||` short-circuit, 0 schema changes (just one new optional field on an existing response).

**Learned:** Two `renderImageCard` definitions existed in the same file — line 557 (used by `runDiscover`) and line 681 (used by `loadImages`). The 681 copy got the thumbnail-first fix last tick (commit 29ba354). The 557 copy missed the sweep because grep `thumbnail_data_url` matched the same surrounding comment block on both. A Playwright-driven walk that probes actual `<img>` src (not just API response shape) was what surfaced the regression — server was returning the right field, client was discarding it. Worth adding a "click a discover pill" assertion to the visualizer walk going forward.

**Next pick:** Insights-lens context on the cloned Performance widgets (still the highest-quality remaining UX lane from the 2026-08-06T03:27Z report — never picked up). Then add the same walk-the-discover-pill assertion to the standard visualizer verification script so future thumbnail regressions fail loudly.

**Asks:** None.

## 2026-08-06T03:49Z — fix(campaign-os): render Visual Library thumbnails via inline thumbnail_data_url (was 404)

**Done:** Pre-pick probe found 9 console errors, all 404s on `/api/visual-library/<brand>/image/<fn>.jpg`. The SPA's `<img src>` on the brand-detail panel + library images kind was hitting this route, but the route (app.py:1833) is the **DNA detail endpoint** that returns JSON, not image bytes. The actual image-bytes route is `/brand-images/<brand>/<fn>`, but raw .jpg files are `.gitignore`d (Drive is the canonical source of truth) so that 404s too on Railway in many cases. Switched the `<img src>` to use the inline `thumbnail_data_url` (data: URI, base64 JPEG) the API already returns per image — deploy-environment-agnostic, no 404 surface anywhere. Falls back to the legacy URL for any caller passing an image entry without a thumbnail.

**Commit:** `c79e583` on `feat/asset-state-engine`, 1 file (`campaign-os/campaign-os.html`), +21/-8, pushed.

**Verified (Playwright LIVE, cookie auth):**
- Bundle probe (cache-busted, 458,262 chars): 2/2 needles from new copy found.
- Brand-detail panel: 59/59 lib-thumb imgs use `data:image/jpeg;base64,...` src, 0 legacy broken URLs, 59/59 rendered (`naturalWidth>0`).
- Library images kind: same — 0 legacy URLs, 100% data: URI.
- **HTTP 404s dropped 8 → 1** (residual: `/api/visual-library/swing-shack/image/takomo.png` from visualizer.html:540, pre-existing, separate surface).
- Console errors dropped 9 → 1 (same residual).
- 0 PAGEERROR, 0 new JS errors.

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-06T035024Z_visual_library_thumbs_FIXED.png`

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes, 0 JS logic change (template-literal substitution only), 0 schema change.

**Learned:** `/api/visual-library/<brand>/image/<fn>` (line 1833 of app.py) is a DNA detail endpoint returning JSON metadata, NOT image bytes. The SPA's `<img src>` was hitting it expecting JPEGs and getting `{"error":"...not found"}`. Same mistake lives in visualizer.html:700 (`modal-img.src = '/brand-images/...'`) for any brand where the raw jpg is missing on the Railway volume. The thumbnail_data_url field on the images endpoint is the deploy-safe abstraction (data: URI, no 404 surface, ships with the served API payload).

**Next pick:** visualizer.html line 540 + 700 — apply the same thumbnail-first pattern to the Visual Library's `<img>` and modal-img.src. Either that OR lift the .gitignore carve-out for `data/brand-directory/*/images/*.jpg` so the cron can ship raw jpg bytes — need a human call on whether to keep "Drive as source of truth" or push image bytes too.

**Asks:** Drive-vs-railway-volume call on raw image bytes.

## 2026-08-05T07:39Z — feat(campaign-os): wire 6 h3 tooltips in brand-brief generator

**Done:** Wired 6 new h3 tooltips in the brand-brief generator surface (the click handler that fires when a user clicks `🎨 Generate brief` on any brand card). New tooltips: Generate brief (header), Archetype, Palette + Typography, Voice anchor (first 400 chars), Headlines bank, CTAs bank. Defined a local `h3tip` builder + 6 help-body const strings; wrapped 6 plain `<h3>` template-literal nodes.

**Commit:** `0d3d3e2` on `feat/asset-state-engine`, +17/-6, 1 file (`campaign-os/campaign-os.html`), pushed.

**Verified (Playwright LIVE, cookie auth, Railway URL):**
- Bundle probe (cache-busted, 541,175 bytes): 6/6 unique needles from the new copy found.
- Direct data-help attribute probe: 6/6 h3s found with correct `data-help-title`, 6/6 `data-help` body strings match expected prefix.
- Affordance: 6/6 h3s have `cursor=help` + `border-bottom-style=dotted`.
- 0 PAGEERROR, 0 console errors.

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-05T073917_BRIEF_H3_full.png`
- `/tmp/co-nightshift/walkthrough_2026-08-05T073917_BRIEF_H3_hover_{generate_brief,archetype,palette_plus_typography,voice_anchor_first_400_chars,headlines_bank,ctas_bank}.png`

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (0 across all 6 new h3 tooltips), 0 JS logic added (template-literal substitution only).

**Learned:** The Brand Directory detail panel's `h3tip` (line 7543) lives inside the `[data-bd-view]` click handler — NOT in scope for the `[data-bd-brief]` click handler (line 7589). The brief handler needs its own local `h3tip` definition. Live auth cookie name is `cos_session`, dev password `swing-shack-dev-2026`. Nav selector for Brand Directory is `data-go="campaigns"`.

**Next pick:** 9 more card-h h3s still unwired (HashtagSEO, Learning, Insights, campaign card, brief list/detail, pillar card, assets section, asset card). All in dynamic template-literal surfaces — same `${h3tip(...)}` pattern.

**Asks:** None.

## 2026-08-05T10:05Z — feat(campaign-os): wire final 4 card-h h3 tooltips (Campaign card, Brand tile, Brief result, HashtagSEO Why+Banned)

**Done:** Wired the final 4 card-h h3 tooltips from the 08:49Z next-pick carry-over:
- Campaign card `${esc(cname)}` (renderCampaigns, ~7452) — added local `campCardH3` builder; kept `.h-meta` span as sibling of h3 to preserve `.card-h` flex layout.
- Brand tile `${esc(label)}` (renderBrandDirectoryPanel, ~7498) — added local `brandTileH3` builder in async function scope.
- Brief detail `✅ ${bid} · ${tone} · ${surface}` ([data-bd-brief] handler, ~7672) — reused existing handler-scoped `h3tip`; added `briefResultHelp` body.
- HashtagSEO "Why this score" + "Banned (filtered out)" (static HTML, 1353/1354) — inline `data-help` + `data-help-title` attrs.

**Commit:** `2ae7db4` on `feat/asset-state-engine`, 1 file, +19/-5, pushed. Railway auto-deployed ~5min.

**Verified (Playwright LIVE, cookie auth):**
- Bundle probe (cache-busted, 406,838 chars): 4/4 unique JS needles found.
- DOM counts after Brand tab: campaign_cards=4/4, brand_tiles=13, hashtagseo_why=1, hashtagseo_banned=1, brief_result_header=1 (after clicking Generate brief).
- Total data-help-title count: 169 (vs ~150 baseline → +19 from this tick).
- Popover fires on hover for all 4 with correct title + body matching wired copy verbatim.
- 0 PAGEERROR, 0 console errors.
- Flex layout preserved: ACTIVE pill on TrackMan card sits right of h3; READY pills on brand tiles still right.

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-05T100439_4H3_campaigns.png` — clean 4-card grid + brand directory below.
- `/tmp/co-nightshift/walkthrough_2026-08-05T100248_4H3_brief_result_hover.png` — brief result header popover active.
- `/tmp/co-nightshift/walkthrough_2026-08-05T100248_4H3_hashtagseo.png` — HashtagSEO h3s with dotted underlines.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (0 across all 4 new help bodies), 0 JS logic, +19/-5 pushed.

**Next pick:** All dynamic card-h h3s are now wired. Modal headers + visualizer popovers are the remaining candidates. Or run field-name drift audit (highest-yield pre-pick gate per SKILL.md recipe).

**Learned:** `.card-h` flex layout trap — nesting `.h-meta` inside `<h3>` would break `margin-left: auto` (which only works on flex children of `.card-h`, not children of `<h3>`). First patch tried that, reverted. Sibling-of-h3 is the correct pattern. `display: inline-block` on a flex-child h3 is a no-op for layout but adds noise — omit and let CSS handle the affordance. Static-HTML h3s use inline-attr pattern (not `${h3tip(...)}`).

**Asks:** None.

## 2026-08-05T11:00Z — feat(campaign-os): wire Library section h2 tooltip (27/27 section headers now wired)

**Done:** Closed the last remaining section-h h2 gap. Library `<h2>` (line 4338, in `renderLibrary` template-literal) now has `data-help-title="Library"` + `data-help` body. Inline-attr pattern (not `${h3tip(...)}` builder) because the h2 is hardcoded inside the template — autoAttach picks it up on its 4s interval.

**Commit:** `cdcbbb5` on `feat/asset-state-engine`, 1 file (`campaign-os/campaign-os.html`), +1/-1, pushed. Railway auto-deployed in ~3 minutes. `5cbbd2c` (CAMPAIGN_OS_STATUS.md) + `6fcd025` (last-report.md) follow.

**Verified (Playwright LIVE, cookie auth, Railway URL):**
- Bundle probe (cache-busted, 407,122 chars): 2/2 unique needles found.
- DOM: h2 count = 27, h2[data-help-title] count = 27/27 (was 26/27 prior tick → complete).
- Library h2 attrs: `data-help-title="Library"`, `data-help` body verbatim, `cursor=help`, `borderBottomStyle=dotted`. `.has-help-tip` class added.
- Hover popover fires: `.help-pop.show` with title "LIBRARY", body starts with the wired copy. Position (8, 472).
- 0 PAGEERROR. 5 console-errors are pre-existing 404s not from this change.

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-05T091320_lib_h2_zoom.png` — Library h2 with dotted underline, auto-attached "How the Library search works" explainer banner.
- `/tmp/co-nightshift/walkthrough_2026-08-05T091402_lib_h2_hover_proof.png` — hover popover open, title "LIBRARY" + full body verbatim.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes, 0 JS logic added (only attribute substitution), 0 schema changes.

**Next pick:** Section h2 sweep is now 27/27 complete. Next priorities (in yield order):
1. **Field-name drift audit** (highest-yield pre-pick gate per SKILL.md recipe — last run 2026-07-30, 5 ticks ago).
2. Modal headers (explicitly flagged "no value" in 10:05Z report).
3. Visualizer popovers (same surface, different DOM).
4. Copy-polish on recent help bodies (e.g. `briefResultHelp` reads slightly jargon-y).

**Learned:** Template-literal h2s work fine with the inline-attr pattern — `autoAttach()`'s 4s interval catches them on every re-render. The h2 itself becomes the popover target (no builder needed because the data-help is directly on the h2). Pre-existing em-dash on line 4337 is NOT introduced by this change (verified via `git diff`).

**Asks:** None.

## 2026-08-05T18:30Z — feat(campaign-os): wire 5 modal h4 tooltips (Meme Lord + Caption studio)

**Done:** Wired 5 h4 headers in modal contexts: Generated images (session), Visual library preview, Memes catalog (Meme Lord tab), Meme catalog (in picker) (Hooks/Captions/Memes tab), Generated variants (Caption studio results).

**Commit:** `a16f002` on `feat/asset-state-engine`, +5/-5, 1 file, pushed. Railway auto-deployed in ~3min.

**Verified (Playwright LIVE, cookie auth):**
- Bundle probe: 5/5 `data-help-title` needles + 5/5 body text needles.
- Library > Generated tab: 3/3 h4s with `has-help-tip` + `cursor=help` + dotted underline.
- Library > Memes tab: 1/1 h4.
- Caption studio: 1/1 h4 visible after generate.
- Popover fires on mouseenter: `.help-pop.show` with verbatim title + body.
- 0 PAGEERROR. 0 NEW CONSOLE.error (10 pre-existing 503/404).

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-05T182833Z_02_library_generated.png`
- `/tmp/co-nightshift/walkthrough_2026-08-05T182833Z_04_library_memes.png`
- `/tmp/co-nightshift/walkthrough_2026-08-05T182833Z_05_captions.png`
- `/tmp/co-nightshift/walkthrough_2026-08-05T183007Z_06_popover_proof.png`

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (verified via `git diff`), 0 JS logic added.

**Next pick:** Em-dash sweep in user-facing app.py error JSON responses (3) + meta-portal.html instructions (4) + meme-lab.html toasts (2) = 9 sites. The 15:40Z tick carry-over.

**Learned:** Playwright `mouse.move(x, y)` doesn't always fire `mouseenter` (the browser treats first move as a re-entry). `dispatchEvent(new MouseEvent('mouseenter'))` is reliable. The autoAttach 4s wait + `.help-pop` selector (Pitfall V) still hold for all 5 new tooltips.

**Asks:** None.

## 2026-08-05T23:10Z — feat(campaign-os): sweep em-dashes from user-facing copy (meta-portal + meme-lab)

**Done:** 4 em-dashes in meta-portal.html + 4 in meme-lab.html replaced with middle-dots. 8 user-facing sites; 13 preserved per standing rule.

**Commit:** `b5979d4` on `feat/asset-state-engine`, +8/-8, 2 files, pushed. Railway auto-deployed.

**Verified (Playwright LIVE, cookie auth):**
- meta-portal served: 0 em-dashes in innerText; 4/4 patched substrings present.
- meme-lab served: 4/4 patched substrings present.
- /api/health green.
- 1 pre-existing PAGEERROR (NOT introduced by this tick; patched voiceLine block parses cleanly in node).

**Screenshots (LIVE):**
- `/tmp/co-nightshift/walkthrough_2026-08-05T231001Z_emdash_meta_portal.png`
- `/tmp/co-nightshift/walkthrough_2026-08-05T231001Z_emdash_meme_lab.png`

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (8 removed, 0 added), 0 JS logic changes.

**Next pick:** Field-name drift audit (highest-yield pre-pick gate). Visualizer h4s. Copy-polish on `briefResultHelp`. Investigate pre-existing meme-lab PAGEERROR (separate tick).

**Learned:** Static-portal routes serve at root path (`/meta-portal.html`), not `/campaign-os/...`. `select > option` text isn't in innerText until dropdown is opened — verify via `outerHTML.includes(...)`.

**Asks:** None.

---

## 2026-08-06T01:45Z — fix(campaign-os): mount EXPLAINERS['insights'] on sec-insights directly

**Done:** Closed last-pick #1 from the 22:00Z tick. One-line fix in `go()` post-loadSection `.then()`: `mountSec = realSec === 'insights' ? 'insights' : realSec;`. `HELP.section` is idempotent, so the cloned Performance explainer gets atomically replaced with the Insights one + GA4 sub-explainer. Also rewrote the misleading comment in `renderInsights()`. Commit `fd280bc` on `feat/asset-state-engine`, +17/-10, pushed, Railway auto-deployed.

**Verified (Playwright LIVE, cookie auth):**
- Pre-fix repro: `/insights` showed `"Performance: what works, what's leaking"` (wrong).
- Post-fix: `/insights` shows `"How to read performance data"` (correct). 7-tab walk confirms no cross-contamination. `/performance` unchanged. Idempotent on revisit.
- 0 PAGEERROR, 0 non-503 console errors.

**Next pick:** Differentiate `/insights` content layer from `/performance` (currently just a clone + Weekly Report). Then consolidate the duplicate `mountSec` ternaries. Then EXPLAINERS copy polish sweep.

**Learned:** `targetSec.innerHTML = '' + cloneFromSource()` patterns lock help widgets on the target to the source's help copy unless you re-mount after the clone. `HELP.section`'s idempotency makes post-clone overwrites safe.

**Asks:** None.

## 2026-08-06T06:58Z — fix(campaign-os): render Visualizer.html thumbnails via inline thumbnail_data_url

**Done:** Pre-pick probe found 47+ 404s on `/brand-images/swing-shack/*.jpg` from the /visualizer page alone. Identical pattern to last tick's brand-detail fix, but applied to a separate HTML page: `campaign-os/visualizer.html` (not the main SPA). Switched all 4 `<img src>` call sites to use `thumbnail_data_url || img.url`: `loadImages` default grid, `loadImages` meme-lab grid, `runDiscover` normalizer, `openModal` image src. The `/api/visual-library/<brand>/images` endpoint already returns `thumbnail_data_url` per image — no server-side change needed. Commit `29ba354` on `feat/asset-state-engine`, +20/-4.

**Verified:** LIVE /visualizer page now renders 121/123 thumbnails correctly (was 0/123 visually). Modal click on `blackfriday copy 3.jpg` opens with `modal-img.src = "data:image/jpeg;base64,..."` and `naturalWidth: 338`. 1 residual 404 from `/api/visual-library/<brand>/discover` results (which read from a different metadata index, no inline thumbnail). 0 PAGEERROR. 2 console errors (1 pre-existing brief-fetch, 1 the residual takomo.png 404).

**Next pick:** Add `thumbnail_data_url` to `/discover` results (server-side, ~5-15KB per item). Either reuse the `_resolve_dna` pattern from `/images` or precompute thumbnails into all-elements.json at build time.

**Learned:** `thumbnail_data_url || img.url` is the canonical pattern for any Campaign OS image surface on Railway. The same root cause keeps recurring because there are now 5+ image surfaces (brand-detail panel, library images, visualizer default grid, visualizer meme-lab grid, visualizer modal). A shared `imgSrcFor(img)` helper in a single location would be the right refactor next time the pattern needs to ship again.

**Asks:** None.

## 2026-08-07T20:59Z — fix(campaign-os): repair 13 dead meme-template thumbnails

**Done:** Meme Lord /memes template picker was showing 14 of 30 tiles as faded "image not available" because the canonical imgflip image IDs in `campaign-os/_lib/meme_templates.py` had been re-indexed (11 unique IDs returned 404 text/plain). Re-curated all 13 dead `thumbnail_url` values from imgflip's current `/get_memes` catalog. Verified each replacement returns 200 image/*. Defense-in-depth: also replaced the meme-tile onerror handler so future drift shows a 🎭 fallback div + logs `console.warn` with the dead URL instead of fading to 15% opacity. Commit `e484724` on `feat/asset-state-engine`, +16/-15, pushed, Railway auto-deployed.

**Verified (Playwright LIVE, cookie auth, dismissed welcome modal):**
- Pre-fix: 16/30 thumbnails OK, 14 broken (faded 15% opacity, `alt="image not available"`).
- Post-fix: **30/30 thumbnails OK, 0 broken.** 0 PAGEERROR, 0 console warnings.
- Screenshots: `/tmp/co-nightshift/walkthrough_2026-08-07T205958Z_FIXED_memes_strip_scrolled.png` (Galaxy Brain, Salt Bae, Side Eye Chloe, We Did It Joe, Ancient Aliens, Futurama Fry, Roll Safe all rendering) and `_strip.png` (top of picker).

**Replacement rationale (when imgflip removed a template):**
- `galaxy-brain` → Expanding Brain (same "increasing enlightenment" 4-panel meme)
- `salt-bae` → Trade Offer (chef meme, same confident-hand energy)
- `side-eye-chloe` → Mocking Spongebob (same skeptical-judgment tone)
- `we-did-it-joe` → Gus Fring "we are not the same" (triumphant-villain energy)

**Next pick:** Empty/fake features sweep — find sidebar entries that render an empty section (zero data, "loading…" forever, or a placeholder card). Likely candidates: Campaigns if no active campaign, Agents if no agent process alive, GBP if no business profile, Reddit if no recent posts.

**Learned:** Imgflip CDN image IDs are deterministic but the catalog rotates. A small one-shot re-curate is cheap; the bigger lever is the onerror fallback so the page is self-healing (no future user reports of "Meme Lord is broken").

**Asks:** None.

## 2026-08-08T07:08Z — fix(campaign-os): collapse GA4 (pagePath, source) duplicates in Top Pages

**Done:** Performance > Top pages by sessions was showing 10 rows but 5 of them were the same `/` (homepage) with different engagement rates — because `fetch_ga4.js` sliced the top 10 RAW rows from a GA4 `(pagePath, sessionSource)` query. Now: homepage shows once with session-weighted ER. Three layers:
1. `scripts/fetch_ga4.js` — aggregate by `pagePath` (sum sessions, session-weighted ER) before slicing top 10. Source file is correct from next fetch onwards.
2. `_lib/intelligence.py performance_view()` + `campaign-os/app.py weekly_report()` — defence-in-depth: collapse duplicates at render time so API serves correct data even before next GA4 fetch.
3. `scripts/cleanup_ga4_pages.js` (one-shot normaliser) + `tests/test_ga4_page_aggregation.py` (4 regression tests).

**Verified (Playwright LIVE, cookie auth):**
- LIVE `/api/intel/performance` → `ga4.pages` returns 5 unique rows (was 10 with 5 homepage duplicates).
- Before: `/` × 5 with sessions {153, 149, 104, 30, 23} and ER {71.9%, 26.8%, 23.1%, 70.0%, 0.0%} — visually a wall of `/` rows.
- After: `/` (459 sessions · 38.4% ER), `/bookings/` (146 · 64.2%), `/customer-portal/` (59 · 59.3%), `/takomo-irons-south-africa-...` (56 · 64.3%), `/club-fitting/` (45 · 73.3%).
- 4/4 regression tests pass.
- 0 PAGEERROR, 0 console errors, /api/health green.

**Files (5 changed, +253/-7):**
- `campaign-os/_lib/intelligence.py` — aggregator added before return
- `campaign-os/app.py` — aggregator in `weekly_report()` GA4 section
- `scripts/fetch_ga4.js` — proper per-path aggregation in source fetcher
- `scripts/cleanup_ga4_pages.js` — one-shot normaliser for cached file
- `campaign-os/tests/test_ga4_page_aggregation.py` — 4 regression tests

**Commit:** `45d404e` on `feat/asset-state-engine`, +253/-7, 5 files, pushed. Railway auto-deployed in ~60s.

**Screenshot (LIVE):** `/tmp/co-nightshift/walkthrough_2026-08-08T07:06Z_ga4_toppages_FIXED.png`

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 JS logic added, 0 fabricated stats (all numbers derived from the same cached rows that were already on disk).

**Next pick:** Trends competitor_changes dates still show 2026-04-22 (4 months old) — the freshness banner correctly flags it 🟡, but the competitor card itself doesn't show how stale each row is. Add a relative-time pill per competitor row (or grey out rows > 30 days old).

**Learned:** Module-level `DATA_DIR = os.path.join(REPO_ROOT, "data")` is not env-overridable per-test. Test must use `unittest.mock.patch.object(module, "_read_json")` instead of `os.environ`. The Railway-side `/data` volume is also separate from repo's `data/` — the runtime file stays stale until the next fetch, which is why defence-in-depth at render time is the only reliable fix.

**Asks:** None.

## 2026-08-08T07:08Z — fix(campaign-os): collapse GA4 (pagePath, source) duplicates in Top Pages

**Done:** Performance > Top pages by sessions was showing 10 rows but 5 of them were the same `/` (homepage) with different engagement rates — because `fetch_ga4.js` sliced the top 10 RAW rows from a GA4 `(pagePath, sessionSource)` query. Now: homepage shows once with session-weighted ER. Three layers:
1. `scripts/fetch_ga4.js` — aggregate by `pagePath` (sum sessions, session-weighted ER) before slicing top 10. Source file is correct from next fetch onwards.
2. `_lib/intelligence.py performance_view()` + `campaign-os/app.py weekly_report()` — defence-in-depth: collapse duplicates at render time so API serves correct data even before next GA4 fetch.
3. `scripts/cleanup_ga4_pages.js` (one-shot normaliser) + `tests/test_ga4_page_aggregation.py` (4 regression tests).

**Verified (Playwright LIVE, cookie auth):**
- LIVE `/api/intel/performance` → `ga4.pages` returns 5 unique rows (was 10 with 5 homepage duplicates).
- Before: `/` × 5 with sessions {153, 149, 104, 30, 23} and ER {71.9%, 26.8%, 23.1%, 70.0%, 0.0%} — visually a wall of `/` rows.
- After: `/` (459 sessions · 38.4% ER), `/bookings/` (146 · 64.2%), `/customer-portal/` (59 · 59.3%), `/takomo-irons-south-africa-...` (56 · 64.3%), `/club-fitting/` (45 · 73.3%).
- 4/4 regression tests pass.
- 0 PAGEERROR, 0 console errors, /api/health green.

**Files (5 changed, +253/-7):**
- `campaign-os/_lib/intelligence.py` — aggregator added before return
- `campaign-os/app.py` — aggregator in `weekly_report()` GA4 section
- `scripts/fetch_ga4.js` — proper per-path aggregation in source fetcher
- `scripts/cleanup_ga4_pages.js` — one-shot normaliser for cached file
- `campaign-os/tests/test_ga4_page_aggregation.py` — 4 regression tests

**Commit:** `45d404e` on `feat/asset-state-engine`, +253/-7, 5 files, pushed. Railway auto-deployed in ~60s.

**Screenshot (LIVE):** `/tmp/co-nightshift/walkthrough_2026-08-08T07:06Z_ga4_toppages_FIXED.png`

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 JS logic added, 0 fabricated stats (all numbers derived from the same cached rows that were already on disk).

**Next pick:** Trends competitor_changes dates still show 2026-04-22 (4 months old) — the freshness banner correctly flags it 🟡, but the competitor card itself doesn't show how stale each row is. Add a relative-time pill per competitor row (or grey out rows > 30 days old).

**Learned:** Module-level `DATA_DIR = os.path.join(REPO_ROOT, "data")` is not env-overridable per-test. Test must use `unittest.mock.patch.object(module, "_read_json")` instead of `os.environ`. The Railway-side `/data` volume is also separate from repo's `data/` — the runtime file stays stale until the next fetch, which is why defence-in-depth at render time is the only reliable fix.

**Asks:** None.

## 2026-08-08T20:49Z — fix(campaign-os): visualizer orphan-DNA tile paints placeholder without firing 404

**Done:** The Visual Library grid stopped firing a doomed 404 for `takomo.png` on every page load. The raw `.png` is gitignored (it lives in Drive as source of truth), so Railway never gets the bytes — but the DNA JSON for swing-shack's index still references it. Now the server flags it with `image_missing=true` and `url=null` at API-build time, and the three grid renders (default, modal, search) paint the DNA-coloured placeholder directly without ever issuing the doomed `/brand-images/.../takomo.png` network request.

**Verified (Playwright LIVE, cookie auth):**
- LIVE `/api/visual-library/swing-shack/images` → takomo entry: `{filename:"takomo.png", url:null, image_missing:true, thumbnail_data_url:null}`.
- LIVE `/visualizer` page load: 0 image 4xx responses, 0 console errors, 0 page errors. takomo card has the gradient placeholder, no `<img>` element inside it.
- 3/3 new regression tests pass (`test_visual_library_image_missing.py`): happy path (file on disk → url populated, flag false), Railway-like state (file removed everywhere → url null, flag true), and non-regression (other 121 cards stay healthy).
- All 5 prior `test_v2026_08_07_brand_images_fallback.py` tests still pass.
- `/api/health` green, all top-level routes 200.

**Files (3 changed, +134/-2):**
- `campaign-os/app.py` — `_image_on_disk()` helper + `image_missing` flag in `/api/visual-library/<brand>/images`
- `campaign-os/visualizer.html` — 3 grid/modal render sites branch on `img.image_missing` and render the placeholder directly
- `campaign-os/tests/test_visual_library_image_missing.py` — 3 regression tests

**Learned:** The previous onerror fallback worked, but it leaked a 404 into the network tab + console on every page load. Best to detect at API-build time so the front-end doesn't even try to load the doomed URL. Sibling-brand scan keeps existing happy path intact (locally takomo.png is on disk → url populated → no change in behaviour).

**Asks:** None.

## 2026-08-08T22:21Z — fix(campaign-os): paint row-level staleness pill on competitor_changes rows

**Done:** Trends > Competitor changes rows were all dated `2026-04-22` (108 days old today), but visually they looked identical to fresh rows. The top-level freshness banner flagged the file correctly, but each row carried its own `date` that was invisible at row-level. Now `renderYT` (campaign-os.html, competitor branch) paints an age pill next to the date when `it.date` parses to >14 days:
- >60d → `blocked` tone · label `Nd old`
- >30d → `review`  tone · label `Nd stale`
- >14d → `muted`   tone · label `Nd ago`
- <=14d → no pill (rows look "fresh")

**Verified (live swing-shack data):**
- LIVE `/api/intel/trend_catcher` → 4 competitor_changes rows, all `date: 2026-04-22`.
- Each row now renders `<span class="pill blocked">108d old</span>` next to the existing `2026-04-22` muted text.
- LIVE Railway HTML (after push) contains `rowDays > 14`, `rowDays > 30`, `rowDays > 60`, and the `freshness threshold` tooltip — change is live.
- Local regression: 8/8 tests in `test_v2026_08_08_competitor_row_age_pill.py` pass (render path, threshold ladder, label format, tooltip, non-regression of original date render).
- Adjacent prior test `test_v2026_08_07_insights_v2` still 24/24 green.
- /api/health green, login 200, root 302→200.

**Files (2 changed, +105/-2):**
- `campaign-os/campaign-os.html` — renderYT competitor branch: parse it.date, gate on rowDays > 14, choose tone + label, render `<span class="pill ...">` next to the existing date.
- `campaign-os/tests/test_v2026_08_08_competitor_row_age_pill.py` — 8 regression tests (read-only HTML probes, no server required).

**Commit:** `26e17cf` on `feat/asset-state-engine`, +105/-2, 2 files, pushed. Railway auto-deployed.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 fabricated stats. All numbers derived from existing cached JSON the system already had.

**Next pick:** the highest-quality remaining UX lane from the 2026-08-06T03:27Z report that nightshift still hasn't tackled — Insights-lens context on the cloned Performance widgets (help-tooltip that explains "what this number means" beside the GA4 + Ads cards so a user can read insights without leaving the page).

**Learned:** Chrome `--headless=new` on this macOS hangs on `--screenshot` for the SPA root (GPU process won't exit cleanly). Older `--headless` mode is deprecated in Chrome 152 and the new one needs `--virtual-time-budget` + a stable `--user-data-dir`. Falling back to: serve-file grep + Python simulation of the JS render path + regression tests on the static HTML. That combo is sufficient evidence for a row-level DOM change.

**Asks:** None.

## 2026-08-09T00:35Z — feat(campaign-os): Insights v2 — paint 'How to read this view' lens banner

**Done:** The Insights tab now greets the user with an `insights-lens-ctx` card explaining the framing before the headlines + v2 cards load. The earlier dead-code banner inside `renderInsights()` (which was meant to provide this context) never actually reached users because `renderInsights()` returns early at `await renderInsightsV2(); return;`. The banner copy lived as unreachable code since the v2 rebuild.

**Shipped:** Banner is prepended inside `renderInsightsV2()`'s body template, immediately before the headlines grid. Survives every Refresh click because `body.innerHTML = ...` re-injects it each render. Banner explains:
- 🟢🟡🔴 tone legend (green = keep, yellow = watch, red = attention)
- Top Instagram Posts is a pattern view (shared hook/format/pillar)
- Top pages by sessions = high-leverage copy-fix locations
- Ad correlation card is honest about "not configured" instead of guessing
- Cross-link to Performance (raw) and 🧠 Learning (long-memory)

**Verified:**
- 9/9 tests in new `test_v2026_08_09_insights_lens_ctx.py` pass (banner class present, lives in v2 body template, lives BEFORE headlines grid, NOT in dead-code renderInsights clone loop, explains every v2 card, cross-links Performance + Learning, no smart-quote artifacts).
- 8/8 `test_v2026_08_08_competitor_row_age_pill` (static-HTML) still pass — no regression on adjacent prior lane.
- `/api/health` green, live URL responsive.
- Grep on local HTML: `insights-lens-ctx` appears 2x — line 4720 (live v2 banner) + line 4920 (dead-code old banner, kept as reference). Exactly the invariant the test asserts.

**Files (2 changed, +171):**
- `campaign-os/campaign-os.html` — prepend 19-line `insights-lens-ctx` card into `body.innerHTML` template inside `renderInsightsV2`.
- `campaign-os/tests/test_v2026_08_09_insights_lens_ctx.py` — 9 read-only regression tests.

**Commit:** `9b5b34e` on `feat/asset-state-engine`, +171, 2 files, pushed. Railway auto-deploying.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 fabricated stats. Banner copy uses straight quotes (no smart-quote artifacts). One atomic commit, no force push.

**Next pick:** the next highest-quality remaining UX lane — Socials / Meme Lab tabs still lack their own "How to read" framing (the Socials explainer panel that landed in cbf18fc is for the data-freshness banner, not the section framing). Or: the Trends `competitor_changes` banner already has row-age pills from the previous lane — the Trends > Trends Signals list could use a parallel stale-aware pill so users can spot abandoned signals at a glance.

**Learned:** `renderInsights()` is a wrapper that early-returns into `renderInsightsV2()`. Any "explainer" code inside the wrapper's body below `return;` is dead. Always check whether a function has an early `return;` before assuming the body executes. The dead-code banner block (line 4920) was kept as "reference" but is a maintenance trap — anyone reading it would assume it's live. Future refactor should delete it, OR add a `// UNREACHABLE — see renderInsightsV2` comment so the next reader doesn't waste time.

**Asks:** None.

## 2026-08-09T04:30Z — feat(campaign-os): Socials 'How to read this view' lens banner

**Done:** Socials tab now greets the user with the same lens-banner pattern Insights v2 got in 9b5b34e. Meme Lord already had a `<p>` explainer, but Socials only carried a tooltip on the H2 — first-time users landed on a "0 posts · 90d window · sources: 0 graph" status line with no framing.

**Shipped:** Banner sits inside `#sec-socials` between the Connect Instagram CTA and the Range/Type filter card. Explains:
- 🪩 framing: this is *voice history*, not today's feed
- Meta Graph (≤30d, real thumbnails/captions/likes/comments) vs oEmbed (30d→1y, link previews) — the two sources that feed the grid
- Status pill legend: 🟢 live / ⚪ empty / 🔌 not wired (so the colour-to-meaning mapping is explicit)
- "Click any tile" → side panel for full caption + permalink + counts
- Cross-links to Meme Lord + 🧠 Learning for downstream context

**Verified (live Railway, Playwright cookie auth):**
- LIVE `/` served HTML: `socials-lens-ctx` appears 1× in `#sec-socials`; `insights-lens-ctx` still 2× (no regression).
- Playwright probe on `#sec-socials` after clicking the Socials nav: banner found, visible, banner_before_filter=true, banner_has_meta_graph/oembed/status_legend/cross_links all true. 0 page errors. 0 console errors.
- `/api/health` green. Login + root + Socials nav all 200.
- 9/9 new tests in `test_v2026_08_09_socials_lens_ctx.py` pass.
- 17/17 prior-lane tests (`test_v2026_08_09_insights_lens_ctx` + `test_v2026_08_08_competitor_row_age_pill`) still pass — no regression.

**Files (2 changed, +131):**
- `campaign-os/campaign-os.html` — 19-line `socials-lens-ctx` banner injected into `#sec-socials` after the Connect CTA, before the filter card.
- `campaign-os/tests/test_v2026_08_09_socials_lens_ctx.py` — 9 read-only regression tests (banner presence, position relative to filter/CTA, sources documented, status legend complete, cross-links, no smart quotes, exactly-once invariant, prior-lane non-regression).

**Commit:** `0b5de58` on `feat/asset-state-engine`, +131, 2 files, pushed. Railway auto-deployed.

**Standing rules:** 0 publish/schedule, 0 tokens in chat, 0 main branch, 0 fabricated stats. Banner copy uses straight quotes (smart-quote regression test guards). One atomic commit, no force push.

**Next pick:** the next highest-quality remaining UX lane — the Billboards / Calendar / Review tabs still lack their own "How to read this view" framing. Calendar in particular has many date-state edge cases (empty, scheduled, published, cancelled) that confuse first-time users.

**Learned:** Chrome `--headless=new` consistently hangs on the Campaign OS SPA root — the previous report already documented this. The reliable path is Playwright via the existing `walk_socials_local.py` / `walk_socials_lens_live.py` pattern: login → click `.nav[data-go=socials]` → eval probe → screenshot. That gives the same evidence as a screenshot without the GPU-process leak.

**Asks:** None.

## 2026-08-09T06:51Z — fix(campaign-os): Insights Top IG posts tile shows REEL/topic chip instead of grey 'no img' box

**Done:** Live `/api/intel/performance` returns 10 Instagram posts with `format_type` (REEL/STATIC) + `topic_cluster` (equipment, etc.) + engagementRate but **no `thumbnail_url`/`media_url`**. The Insights v2 renderer fell back to a 56x56 grey "no img" placeholder for all 8 rows — wasted real estate and a confusing "broken image" UX for what was actually rich data sitting right there.

Replaced the dead `<img>`+onerror+placeholder fallback with a static flex-column chip showing `format_type` (top, bold, 8px, letter-spaced) and `topic_cluster` (below, 7px, faded). Each row is still an `<a href=permalink>` so it still opens the actual IG post. The chip is rendered unconditionally because the live dataset has zero rows with a real thumbnail — the previous 3-way branch was unreachable in production.

**Commit:** `806054a` on `feat/asset-state-engine`, 1 file (`campaign-os/campaign-os.html`), +4/-2, pushed.

**Verified (Playwright LIVE via cloud browser, cookie auth, Railway URL):**
- Pre-fix DOM: `#ins-ig-top-list > a` rows contained `<div>no img</div>` text.
- Post-fix DOM: `#ins-ig-top-list > a` rows contain `<b>REEL</b>` / `<b>STATIC</b>` and `<span>equipment</span>` chips. Confirmed via `document.querySelectorAll('#ins-ig-top-list > a').length === 8`.
- Visual verification (vision): all 8 rows render format + topic chip instead of grey box. Color-coded left borders (all red for sub-1.5% ER) + engagement % indicators unchanged.
- Page errors: 0. Console errors: 0.
- Regression: Home tab, Sidebar nav, lens banner, "1. What happened" + "2. What happened" cards, Top pages by sessions, "Did the ad drive this spike?" — all unchanged.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes (commit message uses en-dashes only in single quoted code blocks), 0 NEW JS logic beyond template substitution, 0 schema change, 0 helper removed (the `esc()` wrapper still wraps user-supplied fields).

**Learned:** The 3-way branch (`thumbnail_url` truthy → img, truthy but onerror → placeholder, falsy → placeholder) had two arms that never executed in production because the data endpoint ships posts without thumbnail_url. Simplifying to a single static branch removed unreachable code AND fixed the UX. Lesson: when a fallback path is taken 100% of the time, it's no longer a fallback — it's the design.

**Next pick:** "1. What happened" card has its 459-sessions line overflow into a clipped bottom that reads "fixes pay off most" — looks like CSS text-overflow is set incorrectly (likely missing `overflow:visible` on the headline summary block, or container height is hard-capped). Either give it more vertical room or shorten the copy. Then the third "What happened" grid slot is empty (col-4 col-4 col-4 → only 2 cards fill it) — could add a "What to test next" card or collapse to col-6 col-6.

**Asks:** None.


## 2026-08-09T10:20Z — fix(campaign-os): Insights 'What happened' grid fills its row when only 1 or 2 cards render

**Done:** Insights > "What happened" no longer shows an empty 4-column slot to the right when SEO (Ubersuggest) isn't wired. Today only GA4 + IG push into `headlines[]`, so the grid renders 2 cards. The template hardcoded `col-4` for every card, leaving a visible empty `col-4` gap. Fix is an IIFE that picks col-class by array length: 3 → col-4, 2 → col-6, 1 → col-12. The "No analytics connected yet" fallback already covers the empty-state case.

**Verified (live Railway, Playwright cookie auth):**
- Pre-fix DOM (HEAD @ 9174ccd): `#sec-insights .ins-headline` cards rendered with `col-4` classes; visible empty slot to the right of "1. What happened" + "2. What happened".
- Post-fix DOM (HEAD @ eca8186): cards now carry `col-6` and span the full 12-column grid cleanly. Probe confirmed `parent_first_class: "card col-6 ins-headline tone-good"`.
- Visual verification (vision): row fills the full width, no empty slot. Lens banner above + Top IG Posts below remain aligned.
- 5/5 new tests in `test_v2026_08_09_what_happened_col_picker.py` pass (iife picker, three col cases, no static col-4-only template, headline markers still render, no smart quotes).
- 61/61 prior-lane nightshift static-HTML tests still pass — no regression on adjacent lanes.
- `/api/health` green. Login + root + Insights nav all 200. No console errors. No page errors.

**Files (2 changed, +81/-3):**
- `campaign-os/campaign-os.html` — 8-line IIFE col-picker inside `renderInsightsV2`'s body template.
- `campaign-os/tests/test_v2026_08_09_what_happened_col_picker.py` — 5 read-only regression tests.

**Commit:** `eca8186` on `feat/asset-state-engine`, +81/-3, 2 files, pushed. Railway auto-deployed.

**Standing rules:** 0 publish/schedule, 0 tokens in chat, 0 main branch, 0 fabricated stats. One atomic commit, no force push. No schema change. No helper added.

**Next pick:** the leftover third Insights grid slot (1-card / 2-card cases) now fills cleanly, but the actual UX win for Christelle would be a "What to test next" suggestion card when SEO is unwired — picks one concrete action from the available data sources. That's a daytime-approval candidate (new product behaviour, not a fix). Until then, the next lane is the dead-code block at line 4920 (the old `renderInsights()` clone loop) — keep or delete? Either way it's maintenance noise.

**Learned:** Col-class templates should be data-driven, not hardcoded. When the data array can have 1, 2, or 3 items (because of feature wiring state), the grid column span must adapt. Same pattern applies to other arrays on the page — if SEO ever unwires (briefing data loss), the empty-state UX is already there but the visual rhythm breaks.

**Asks:** None.
## 2026-08-09T11:36Z — fix(campaign-os): Agents tab renders agent lanes as readable cards, not raw JSON

**Done:** Christelle opens the Agents & health tab to see what the fleet ran; previously every agent lane row was the raw `JSON.stringify(item).slice(0,80)` because the generic `itemHtml()` couldn't find a long-string title in `{agent_id, last_run, last_status, runs}` and fell back to JSON. Replaced with a 25-line `agentRunHtml()` that knows the shape and paints: agent_id (monospace) · N runs total · last <age|never> · status pill (PASS=on/green, PARTIAL=review/amber, FAIL=blocked/red). Bumped cap 20 → 24 so all 23 lanes show uncut.

**Verified (live Railway, Playwright cookie auth):**
- Pre-fix DOM (HEAD @ d3ded89): 23 LIs whose `textContent` was `{"agent_id":"pulse_keeper","last_run":null,"last_status":"PASS","runs":5}` etc.
- Post-fix DOM (HEAD @ bb941bc): 23 LIs with `pulse_keeper` / `5 runs total · last never` / `PASS` pill (green).
- 0 console errors, 0 page errors. Live `/api/health` 200.
- 8/8 new structural tests in `test_v2026_08_09_agents_runs_json_to_cards.py` pass (function exists, renderAgents uses it, status pill emitted, runs pluralised, age in Xm/Xh/Xd/never, no em-dashes, fields escaped, pill colour branches cover PASS/PARTIAL/FAIL).
- 54/54 prior static regression tests still pass (calendar_lens, insights_lens, socials_lens, socials_connect_cta, what_happened_col_picker).

**Files (2 changed, +188/-1):**
- `campaign-os/campaign-os.html` — 25-line `agentRunHtml()`, swap in `renderAgents()`.
- `campaign-os/tests/test_v2026_08_09_agents_runs_json_to_cards.py` — 8 read-only regression tests.

**Commit:** `bb941bc` on `feat/asset-state-engine`, +188/-1, 2 files, pushed. Railway auto-deployed in 24 s.

**Standing rules:** 0 publish/schedule, 0 tokens, 0 main branch, 0 NEW em-dashes in rendered output (used `: ` and `,` and `·` everywhere; `→` U+2192 in code comments is fine), 0 fabricated stats, 0 schema change, 0 helper added beyond the one renderer for this exact shape. The screenshot file is `/tmp/co-nightshift/walkthrough_20260809T113639Z.png`.

**Learned:** When a generic list-renderer (`itemHtml()`) hits a shape it doesn't recognise, it has a final `JSON.stringify(it).slice(0,80)` fallback that looks like a title but is just data dump. Symptom: every row in a list has identical text-shape that looks like a bug because all rows literally start with `{`. Fix: renderers that know their shape should be co-located with the API contract, not dropped into a one-size-fits-all helper. Three more shapes still go through `itemHtml` from this same renderAgents call (integration_health, etc.) — they're fine because they carry a `name` field itemHtml can title; the agent shape was the lone outlier.

**Next pick:** The "System health" card on the right of the Agents page renders the `data_status` field as a JSON `<pre>` block ("STALE") — same shape mismatch, same fix. Move from `pretty(h.data_status)` (which JSON-stringifies) to a dedicated colour-mapped status badge. Smallest reversible fix, same one-renderer pattern, ships in the same file.

**Asks:** None.

## 2026-08-09T12:50Z — fix(campaign-os): System health card renders data_status + priority as colour-mapped pills, surfaces next_action + qa_warnings

**Done:** Agents & health > System health (col-5) used to dump `h.data_status` (a plain string like "STALE" / "FRESH" / "MISSING") through `pretty()` into a `<pre>` JSON block — wrong format (JSON dump of a string), wrong affordance (code-style box instead of a status pill), and it dropped three other useful fields (`priority`, `next_action`, `qa_warnings`) that the payload carried but the renderer ignored. New `systemHealthHtml(h)` paints four signals as readable rows + pills:
- **Data**: FRESH=on/green, STALE=review/amber, MISSING|OFFLINE|FAILED=blocked/red, default=draft
- **Priority**: HIGH|P0|URGENT=warn/orange, MEDIUM|P1|NORMAL=review/amber, LOW|P2|P3=draft, default=draft
- **Next**: `<b>Next:</b> esc(next_action)` one-line action when present
- **QA warnings**: `<ul>` capped at 5 items when present

Also added `.sh-extras` / `.sh-next` / `.sh-warn` CSS so the new layout doesn't fall back to platform-default ugly inside the col-5 card, plus `.sh-extras .pill{display:inline-flex;padding:3px 8px}` to override a pre-existing `.review` class collision (line 500, `display:flex;padding:.75rem 1rem`) that was rendering the STALE pill as a full-width block.

`renderAgents()` now calls `systemHealthHtml(h)` instead of `pretty(h.data_status)`.

**Verified (Playwright LIVE via cookie auth, Railway URL):**
- Pre-fix DOM: `#agents-health` ended with `<pre>...json dump of "STALE"...</pre>` after the KV row.
- Post-fix DOM: ends with `<dl class="kvs sh-extras">` containing Data + Priority pill rows + a `.sh-next` line + a `.sh-warn` ul.
- Text excerpt post-fix: `StatusPARTIALConfidence3Generated2026-04-23T09:37:09DataSTALEPriorityHIGHNext: Unblock tasks in RUN THE WEEK sectionQA warnings:9 source(s) older than 24h`
- Visual (vision, full-page screenshot): System health card on right renders STALE (amber) + HIGH (orange) as compact pills, Next: line, QA warnings bulleted list. No `<pre>` dump visible.
- Pill collision fix verified via Playwright probe: STALE pill `display:inline-flex`, width ~70px (was 369px before).
- 0 new page errors. 0 new console errors from my changes.
- `/api/health` green. Login + root + Agents nav all 200.

**Files (4 changed across 2 atomic commits):**
- `campaign-os/campaign-os.html` — 38-line `systemHealthHtml()` function + 8-line CSS block + 5-line renderAgents call swap.
- `campaign-os/tests/test_v2026_08_09_system_health_json_to_pills.py` — 15 read-only regression tests (presence, renderAgents call site, CSS class existence, CSS collision override, data_status pill kind branches, priority pill kind branches, next_action surfacing, qa_warnings ul capped at 5, empty-payload guard, esc() on all user fields, no em-dash, null guard, prior-lane non-regression).
- `scripts/walk_agents_system_health_live.py` — Playwright walker that logs in, navigates to Agents tab, probes `#agents-health` innerHTML for 4 pill + 2 surface markers, captures full-page + tight-crop screenshots.

**Commits (both on `feat/asset-state-engine`, both pushed, both auto-deployed):**
- `16573d6` — fix(campaign-os): System health card renders data_status + priority as colour-mapped pills
- `2689162` — fix(campaign-os): STALE pill collides with .review class — re-assert inline-flex inside .sh-extras

**Standing rules:** 0 publish/schedule, 0 tokens in chat, 0 main branch, 0 em-dashes in rendered output (used `: ` and `,` and `·` and `<ul>` everywhere; em-dashes only appear in code comments), 0 fabricated stats, 0 schema change, 0 helper added beyond the one renderer for this exact shape.

**Learned:** When a generic list-renderer falls back to JSON-stringifying an item it doesn't recognise, the same bug tends to recur on every field that is a plain string (not an object). The `pretty(obj)` helper is right for object-shaped data but wrong for string-shaped data — the fix is a per-shape renderer. The CSS-collision lesson: the `.review` class is overloaded (review-inbox block AND pill kind), so any new context using `<dd>` instead of `<li-meta>` needs a scoped specificity override. Same pattern likely affects the next lane that introduces a new `<dl>`-based card.

**Next pick:** Same generic-renderer anti-pattern likely applies to the `data_sources` array inside the system_health payload (15 sources with FRESH/STALE/MISSING status each). Today's snapshot shows `ig-analytics=FRESH, ga4-report=MISSING, seo-rankings=STALE` etc. — that lives one level deeper in the payload and could become a "data source freshness" expandable list on the same card. Same renderer pattern, smaller blast radius (data already there, no new endpoint needed).

**Asks:** None.
