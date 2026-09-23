# Campaign Heroes P10 — show every image that can actually load

**Date:** 23 September 2026  
**Depends on:** P9 + P8f live on `origin/main` (`3a9b18ca`)  
**Do not** flip `HEROES_CUTOVER` · **do not** enable live Postiz · **do not** delete leftover HTML

Kyle: Daily ticker / Review still have no pictures. “Get what can show showing.”

## What exists on live (checked 2026-09-23)

| Source | Count | Browser |
|---|---|---|
| Library JPG e.g. `/brand-images/stick/stick_ballfittingpost.jpg` | many | **200** |
| Inbox `meta.image_url` `gen-*.png` | Stick 11 / Swing 25 | **404** — Flask only reads bundled `data/`, gens written to `$DATA_DIR` |
| Daily ticker / Review `QueueItem` | — | **no `<img>` at all** |
| Review piece | — | `assetVisualUrl` reads camelCase only, ignores `meta.image_url` |
| Daily “What worked” | 3 squares | `InsightPostThumb` — IG CDN; **“no thumb”** if URL missing/broken |

Classic felt full because Visual Library used `/api/visual-library/<brand>/image/<file>` (and data-URLs). Heroes lists never drew a picture.

## Goal

Show every URL that loads. Hide every URL that 404s. Do not invent art.

1. **`GET /brand-images/<brand>/<file>`** also looks in `$DATA_DIR/brand-directory/<brand>/images` then bundled (same pattern as `/assets/`). Traversal still 403.
2. **`assetVisualUrl`** also reads snake_case `image_url` / `image_path`.
3. **`QueueItem`** optional `thumb` — 64px `<img>`, `onError` hide (no broken icon, no “no thumb” on the list).
4. **Daily ticker + Review queue** pass `item.meta?.image_url` (and camelCase if present).
5. **Review piece** fallback: `assetVisualUrl(asset) || item.meta?.image_url`.
6. **Daily “What worked”** — if an IG post has no usable src after P9 fallbacks, **do not** render a “no thumb” square. If fewer than 3 IG thumbs, fill remaining slots from **visual library** images that have a working `url` / `thumbnail_data_url` (library photos that already 200). Caption the strip so IG vs library is obvious if mixed.

## Files

| Item | Path |
|---|---|
| Serve DATA_DIR | `campaign-os/app.py` `brand_image_serve` ~1960 |
| Test | `campaign-os/tests/test_v2026_08_07_brand_images_fallback.py` (extend) |
| URL helper | `web/src/lib/api.ts` `assetVisualUrl` + `CampaignAsset` |
| List chrome | `web/src/components/ui.tsx` `QueueItem` |
| Lists | `web/src/pages/Daily.tsx`, `web/src/pages/Review.tsx` |
| Detail | `web/src/pages/ReviewPiece.tsx` |
| What worked | `web/src/pages/Daily.tsx` + `InsightPostThumb` (hide empty) |
| DESIGN.md | one line: list thumbs hide-on-error |

## Out of scope

Live Postiz, HEROES_CUTOVER, deleting HTML, spawning COS agents on Linux, re-running `draft_assets` (spend cap). Do not hammer image gen.

## Done

Library photos and any `gen-*` that exist on the volume load in Review list + ticker + piece. Broken `gen-*` 404s are hidden. What-worked never shows three empty “no thumb” squares when library photos exist. Verify PASS. feat → integrate. Kyle gates `main`.
