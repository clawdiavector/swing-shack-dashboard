# Postmortem: Weekly Marketing Report — dashboard automation

**Date:** 2026-07-30
**Commits:** `47d28da` (branch) → `9bdc04e` (main)
**Branch:** feat/asset-state-engine → main
**Status:** ✅ Live on Railway (pending manual redeploy) + localhost

## What user asked
"This is what my weekly marketing report looks like — I want this to be
automated in the dashboard too." User did not attach an image but said
existing weekly reports exist at `data/weekly-report.md`. That existing
file was authored by the `weekly_reporter` agent — sparse manual format.

## Decision
Build a JSON aggregator that mirrors the structure of the existing
weekly markdown report, expose it as a dashboard card in the Insights
tab, and add a markdown export endpoint that also persists the file.
Don't replace the `weekly_reporter` agent — they coexist (the agent
will overwrite my export when it runs, which is the right behavior).

## Files
- `campaign-os/_lib/intelligence.py` — new `weekly_report()` function
  + `_parse_iso_date()` helper. ~230 lines. Reads from `data/`:
    - `published-items.json` → published count + top hooks/CTAs
    - `publish-failures.json` → failure count
    - `agent-runs.json` → per-agent pass/fail/partial
    - `hook-bank.json` → hook text lookup
    - `seo-rankings.json` → rising/falling keywords
  - Registered in `INTELLIGENCE_FUNCS` as `"weekly_report"` (auto-routed
    via `/api/intel/<name>`).
- `campaign-os/app.py` — added `weekly_report_export()` route at
  `/api/intel/weekly_report/export`. Returns markdown, persists to
  `data/weekly-report.md`. Imported `Response` from flask.
- `campaign-os/campaign-os.html` — added `renderWeeklyReport()` that
  builds the live card into `#sec-insights` after `renderInsights()`
  clones the performance section.

## Behavior
**JSON view (`GET /api/intel/weekly_report`)** returns:
- `headline_kpis` — published, failed, win_rate_pct, agent_runs, agent_pass_rate_pct
- `platforms` — {instagram: N, facebook: M}
- `by_day` — {Mon..Sun: N}
- `top_hooks` — top 5 most-used, with text from hook-bank
- `top_ctas` — top 5 most-used
- `seo_movers` — rising + falling keywords
- `failures` — last 10 failed publishes with reason
- `agent_breakdown` — per-agent pass/fail
- `week_on_week` — curr/prev/delta/pct_change for headline metrics
- `headline` — single sentence summary

**Markdown export (`GET /api/intel/weekly_report/export`)** — same data
formatted as markdown. Saved to `data/weekly-report.md` automatically.
Downloaded via the Export button on the card.

**Dashboard card** — inside the Insights tab, beneath the Explain panel:
- Header: 📅 Weekly marketing report + date range + ⬇️ Export button
- 4 KPI tiles
- Platforms / Top hooks (two columns)
- SEO movers / Failures (two columns)
- WoW strip at the bottom

Empty sub-sections (Top hooks, SEO movers, Failures) collapse
automatically via the `.card:has(> ul > li.empty:only-child)` CSS
from commit d2545a1.

## Verified
- ✅ Live tunnel screenshot shows the card rendering with date range,
  Export button, KPIs, WoW strip
- ✅ `/api/intel/weekly_report` returns 200 with full payload
- ✅ `/api/intel/weekly_report/export` returns 200 with valid markdown
- ✅ `data/weekly-report.md` is being persisted
- ✅ Empty sub-sections collapse cleanly
- ✅ Pushed to origin main at `9bdc04e`

## Known limitations
- **This week's data is sparse** because all `published-items.json`
  entries are dated March-April. The aggregator reads them correctly
  (WoW shows `prev: 57`) — it's just that nothing has been published
  in the last 7 days. Card will fill automatically as publishing
  resumes.
- The card's headline reads "Quiet week — 0 agent runs, no publishes
  attempted" when there's no activity. Could be more opinionated
  (e.g. "Saturday 2 weeks ago you shipped X — want to do it again?")
  but that's a follow-up.
- SEO movers show nothing because `seo-rankings.json` is from
  April. Not a code bug — the data is stale.
- The Insights tab still says "Performance signals" in the H2
  immediately above the weekly report. Minor cosmetic.

## Followups (deferred — not on this fix list)
- Add a "Send to Slack" button that posts the markdown export
- Add date-range picker (last 7 / 30 / 90 days / custom)
- Add per-brand tabs if multi-brand setup needs them
- The three bugs from earlier turns (Insights blank, Viz 0-filtered,
  Meme placeholders) are still pending. Ask which to tackle next.
