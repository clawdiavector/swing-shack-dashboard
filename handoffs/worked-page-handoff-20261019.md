# Handoff: What worked page, 19 Oct 2026

**Branch:** `fix/worked-recipes-honest` (commit `8d7e3c6c`), cut from `origin/main` (`1b465a09`). Pushed, no PR, not merged. `main` untouched.

## What is done
- **Recipes tab:** the weekly "21 recommendations published this week" count (kind `signal`) no longer sits under "What worked". Real results go under "What worked" (empty state: "No scored winners yet. The Posts tab shows which Instagram posts have worked."). Counts move to "Weekly signals (not results)" with a note that they are not measured outcomes.
- **Learn summary:** one line under the verdict explains OK / LATE / FAILED / NEVER. LATE = samples are in, but no recipe is ready yet.
- File changed: `web/src/pages/results/Worked.tsx` only.

## Already on main (do not redo)
PRs #115 and #116 added: caption first, rank, brand label, verdict-coloured badge, "why these worked" strip, ratio to the average, and the plural fix. The posts-card audit (`CampaignOS/research/worked-posts-card-audit-2026-10-16.md` in the wiki) is mostly resolved.

## Checked
- `tsc -p tsconfig.app.json --noEmit`: passes.
- Not checked: browser preview, live Railway, or the real data behind the Recipes tab. The filter assumes the live file marks counts with `kind: "signal"`; the existing test fixture does, but live data was not read.
- ESLint is not installed in `web/`, so no lint run.

## Still open (needs a decision)
1. Cut Recipes, CTAs and Patterns from the page, or keep them with a "no data since August" note? (Christelle prefers few tabs.)
2. Posts card: median or mean average? Which window (last 90 days)?
3. Make-another-like-this: production `meta-index` has no post-to-template links (18 external posts, index built 22 Sep). The button needs the publish step to record media ID, asset ID and template ID first.

## How to verify
1. `git fetch && git checkout fix/worked-recipes-honest` (or use the worktree at `C:\w\wr`).
2. Open What worked > Recipes on live Railway after merge, and check the signal count sits under "Weekly signals (not results)".
3. Check the Learn summary line reads sensibly for the current verdict.

## Related
- Wiki: `CampaignOS/research/worked-page-tabs-audit-2026-10-19.md` (committed locally, not pushed: wiki sync failed).
- Wiki: `CampaignOS/research/post-to-template-link-2026-10-19.md`.
