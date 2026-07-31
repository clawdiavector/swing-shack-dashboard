# Postmortem: Collapse empty cards to slim banners

**Date:** 2026-07-30
**Commit:** `d2545a1`
**Author:** Heidi (orchestrator)
**Type:** UX cleanup

## Problem
User reported "big empty space next to the nav bar in almost each section."
Root cause: when a card has no items, the empty-state `<li class="empty">`
sits in the middle of a full-height `.card` (~280px tall) with mostly
blank space above and below. Especially visible on the home dashboard
where 6 cards (Do first, Needs review, Ready to publish, High-impact
misses, SEO quick wins, Post today) each occupy 50% of their row.

## Decision
User chose **Option A** (5-min fix): collapse empty cards to slim banners
instead of removing or replacing them. Keeps the title so user still knows
which section is empty.

## Implementation
- Single CSS block (13 lines) using `:has()` selectors
- Targets BOTH home-page pattern (`<div class="card"><ul class="list"><li class="empty">...`)
  AND other-section pattern (`<div class="card"><div><div class="empty">...`)
- No JS changes, no template changes — works retroactively for every section
- Result: empty card drops from ~280px to ~50px (–82%)

## Why CSS-only (not JS)
1. Single source of truth — one rule covers 61 `.empty` occurrences
2. Survives future section additions automatically
3. No template-literal refactor risk (the home render is a complex string)
4. Modern browsers all support `:has()` (Chrome 105+, Safari 15.4+, FF 121+)

## Visual treatment
- Reduced padding (`.45rem .85rem`)
- Faded background (`rgba(255,255,255,.025)`)
- Dashed border signals "empty, not broken"
- Title faded to `opacity: .6`, smaller font (12px)
- Empty text inline next to title, italic, tx-3 color

## Verified
- ✅ Live tunnel screenshot shows empty cards collapsed to ~50px
- ✅ Cards with content (Do first, High-impact misses, Post today) still
  render full-height normally
- ✅ Fix is universal — applies to all 61 `.empty` occurrences across
  Review, Publish, Insights, Trends, Ideas, Performance, etc.
- ✅ Pushed to `origin/main` at `d2545a1`

## Followup
- "Post today" still has 5 stale captions — separate cleanup task
  (already on priority list as item #5).
- Sidebar still has 28 items (target ~8) — separate cleanup task
  (already on priority list as item #8).
