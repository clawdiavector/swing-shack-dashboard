# Nightshift Report — 2026-08-06T03:49Z

## ✅ Done
Fixed 8 broken-image 404s on the brand-detail panel + library images surface by switching `<img src>` from `/api/visual-library/<brand>/image/<fn>` (returns JSON, not bytes) to the inline `thumbnail_data_url` (data: URI) the API already returns per image. Raw .jpg files are `.gitignore`d (Drive is source of truth), so even the alternative `/brand-images/<brand>/<fn>` route 404s on Railway. Using the thumbnail makes the surface deploy-environment-agnostic.

## 🎯 Verified (Playwright LIVE, cookie auth, Railway URL)
- Bundle probe (cache-busted, 458,262 chars): 2/2 unique needles from new copy found.
- Brand-detail panel: 59/59 lib-thumb imgs use `data:image/jpeg;base64,...` src, 0 legacy broken URLs, 59/59 rendered (`naturalWidth>0`).
- Library images kind: same — 0 legacy URLs, 100% data: URI.
- **HTTP 404s dropped 8 → 1** (remaining: `/api/visual-library/swing-shack/image/takomo.png` from `visualizer.html:540`, pre-existing, separate surface).
- Console errors dropped 9 → 1 (same residual as above).
- 0 PAGEERROR, 0 new JS errors.

## 📁 Commit
`c79e583` on `feat/asset-state-engine`, 1 file (`campaign-os/campaign-os.html`), +21/-8, pushed. Railway auto-deployed.

## 📸 Screenshot (LIVE)
- `/tmp/co-nightshift/walkthrough_2026-08-06T035024Z_visual_library_thumbs_FIXED.png`

## 🎯 Next
- Visualizer.html line 540 (`/brand-images/...`) also 404s for takomo.png — separate pre-existing image-storage drift on Railway volume. Same fix pattern (use thumbnail_data_url from API response) is the right move.
- Or: ship the missing raw .jpg files via the daily cron and remove the .gitignore carve-out so the canonical image-bytes route starts working too. Need a human call on whether to lift the "Drive as source of truth" invariant.

## 🧠 Learned
The route `/api/visual-library/<brand>/image/<fn>` (line 1833 of `app.py`) is a **DNA detail endpoint** returning JSON (the metadata layer for the modal), NOT image bytes. The SPA's `<img src>` was hitting this route expecting JPEGs and getting `{"error":"...not found"}`. The same mistake is now confirmed on `visualizer.html:700` (`modal-img.src = '/brand-images/...'`) for any brand where raw jpg is missing. The thumbnail_data_url field on the images endpoint is the deploy-safe abstraction.

## 🚨 Asks
Should the .gitignore carve-out for `data/brand-directory/*/images/*.jpg` be lifted (let the cron ship jpg bytes to Railway) — OR should visualizer.html + any future surface use the thumbnail_data_url pattern instead? Both are fine; it's a one-time decision about where image bytes canonically live.