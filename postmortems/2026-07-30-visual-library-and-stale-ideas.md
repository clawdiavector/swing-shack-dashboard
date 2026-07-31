# Postmortem: Visual Library schema fallback + stale post_today filter

**Date:** 2026-07-30
**Commits:**
- `a720e85` — visual-library schema fallback for stats + images
- `9048ac5` — `_filter_fresh_ideas` helper, applied to morning_brief + opportunities_view
- `a6f2b39` — merged into main

## Problem 1: Visual Library filter dropped everything to 0

User screenshot showed: 122 total images, 0 filtered, 0 products, "No
images match current filter." Clicking a product chip confirmed it
filtered down to 0 every time.

Root cause: schema mismatch. Real dissector output writes
`layer4_products.detected_brands[]` (list of brand strings). The
`/api/visual-library/<brand>/stats` and `/images` endpoints read
`layer4_products.products[]` (list of {name: ...} dicts). Result:
stats returned `products: {}`, product filter applied against an empty
list, dropped everything.

The earlier image-search rebuild (`3a492fd`) had the right schema
fallback but only patched `/api/visual-library/search` (the new route).
The pre-existing `/stats` and `/images` routes still had the old logic.

Fix: mirror the schema fallback to both endpoints, and add the same
fallback for OCR (`lines[]` vs `text_preview`).

## Problem 2: Post today showed 5 stale hooks

User screenshot showed 5 "Post today" captions dated from June 2026,
all `used: false`. Two months old.

Root cause: `morning_brief()` read `content-ideas.json.post_today` raw,
with no staleness check. `post_today` is a sliding pool but nothing
ages items out.

Fix: `_filter_fresh_ideas(items, days=14)` drops items where `used=True`
OR whose `idea_id` date prefix (`YYYY-MM-DD`) is older than 14 days.
Applied to both `morning_brief()` and `opportunities_view()` (which
feeds the Ideas tab).

## Files
- `campaign-os/app.py` — schema fallback for `/stats` and `/images`
- `campaign-os/_lib/intelligence.py` — `_filter_fresh_ideas` helper
  + applied to `morning_brief()` and `opportunities_view()`

## Verified
- ✅ `/api/visual-library/swing-shack/stats` returns 11 products with
  real counts (was `{}`)
- ✅ GTS Putter filter returns 18 images (was 0)
- ✅ `/api/intel/morning_brief` `post_today` count drops from 5 → 0
- ✅ "📮 Post today" card on home dashboard collapses to slim
  empty-state banner via the `:has()` CSS from d2545a1
- ✅ All three empty cards (Needs review, Ready to publish, Post today)
  are slim banners
- ✅ Pushed: `a6f2b39` on `origin/main`

## Followups (still pending)
- 30+ duplicate Review rows — needs Review queue fix, user call needed
- Generator button clicks on Create page — need to repro
- Emoji soup cleanup — need to see
- Zero-state Insights cards — stat-card layout investigation
- Image Generator wiring — needs API key direction
- Meme Lab placeholder images — needs decision on whether to scrape
  real templates
