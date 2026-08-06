# Nightshift Report — 2026-08-06T06:16Z

## ✅ Done
Two-part fix that closes the last residual 404 on the Visualizer (the `takomo.png` outlier flagged in last tick's report).
1. **Server** (`app.py`): `/api/visual-library/<brand>/discover` now mirrors the `/images` endpoint pattern — resolves each entry's DNA JSON (with the Railway-safe `_resolve_dna` fallback), extracts `thumbnail_b64`, ships it as `thumbnail_data_url: data:image/jpeg;base64,...`.
2. **Client** (`visualizer.html` line 557): `renderImageCard` was rendering discover results with a stale `<img src=${img.url}>` — never the data-URI preference. Added the same `imgSrc = img.thumbnail_data_url || img.url` short-circuit the `loadImages` render at line 681 already had.

## 🎯 Verified (Playwright LIVE, cookie auth, Railway URL)
- **Default grid:** 122 cards, **121/122 use `data:image/jpeg;base64,...` src, naturalWidth>0** (the 1 missing = `takomo`, its DNA file legitimately has no `thumbnail_b64` field — data condition).
- **Discover grid** (after clicking a color filter pill, 42 results): **42/42 use `data:image/jpeg;base64,...` src, naturalWidth>0** (was 0/42 before the client fix).
- **Modal** (first discover card click): `data:image/jpeg;base64,...` src, `naturalWidth: 540`.
- **HTTP 404s on `/brand-images/`** during discover flow: 1 (just the takomo.png data condition).
- **PAGEERROR:** 0. **Sibling endpoints** (`/images`, `/recipe`, `/stats`, `/brands`): all 200.

## 📁 Commits (both on `feat/asset-state-engine`, pushed, Railway auto-deployed)
- `9174d60` — server: discover endpoint ships `thumbnail_data_url` (1 file, `app.py`, +30/-1)
- `164479e` — client: renderImageCard prefers `thumbnail_data_url` (1 file, `visualizer.html`, +6/-1)

## 📸 Screenshots (LIVE)
- `/tmp/co-nightshift/walkthrough_discover_01_visualizer_default.png` — default grid, 121 data URIs
- `/tmp/co-nightshift/walkthrough_discover_02_after_filter.png` — after blue-color discover pill, 42 data URIs
- `/tmp/co-nightshift/walkthrough_discover_03_modal.png` — discover-result modal

## 🎯 Next
1. **Insights-lens context on the cloned Performance widgets** (still the highest-quality remaining UX lane from the 2026-08-06T03:27Z report — never picked up).
2. **Add a "click a discover pill" assertion** to the standard visualizer verification script so future thumbnail regressions fail loudly — caught this one only because Playwright probed actual `<img>` src, not just API shape.

## 🧠 Learned
Two `renderImageCard` definitions existed in the same file — line 557 (used by `runDiscover`) and line 681 (used by `loadImages`). The 681 copy got the thumbnail-first fix last tick; the 557 copy missed it because `grep thumbnail_data_url` matched the same surrounding comment block on both. The server returned the right field; the client was discarding it. Worth a discover-pill probe in the visualizer walk.

## 🚨 Asks
None.