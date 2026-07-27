# Campaign OS · Overnight CTO Build — Status & Continuation

## Last update
2026-07-27 · CTO overnight build · MiniMax-M3 (continuation session)

## Overnight cron
- Job ID `da7bebf99c66`, hourly 22:00–10:00 SAST, 12 ticks, delivers to Discord origin.
- Each tick: reads this file, builds one major feature end-to-end (frontend + backend + UX), commits + pushes, appends status block.

## What is running right now
- **Server**: `python3 campaign-os/app.py` on port 8765 (PID 73081, alive)
- **Branch**: `feat/asset-state-engine` (local + remote at `0bf8dfa` — Step 105A deployment)
- **Working tree**: dirty (has uncommitted `intelligence.py` + `campaign-os.html` + `app.py` edits from previous session)
- **Live URL (last tunnel)**: `https://que-wesley-caribbean-dts.trycloudflare.com` (may be expired — re-launch with `cloudflared tunnel --url http://127.0.0.1:8765`)

## What is shipped (verified alive in browser)
- **Single SPA**: `campaign-os/campaign-os.html` (~75KB, dark modern design)
- **23 intelligence endpoints** under `/api/intel/<view>` — all 200
- **Universal search**: `/api/search?q=`
- **Sidebar nav**: 21 entries (Brief, Review, Publish, Calendar, Trends, Ideas, Performance, Learning, Hooks, Memes, Billboards, Captions, Headlines, CTAs, SEO, GBP, Reddit, FAQs, Postiz, Campaigns, Agents)
- **Morning Brief**: 4 stat cards + 🔥 Hot trends ticker + 6 widget cards (Do first / Needs review / Ready / Misses / SEO wins / Post today)
- **Calendar**: 56 slots across 14 days (4/day), today highlighted, prev/today/next nav
- **Performance**: live IG avg ER, top posts with real captions + engagement, SEO rising/falling/keywords, A/B tests, GA4 pages, **natural-language insights** ("'…' is performing 310% better than your Instagram average.")
- **Hook Bank**: 89 hooks in 3 buckets + formulas + ⚡ Generate 10 fresh from signals → works
- **Caption Studio**: bank + CTAs + per-asset **⚡ Generate 5 caption variants** → works (tested: returned real hook + body + CTA for `takomo-101t-hook-a`)
- **Trend Catcher**: 8 YouTube trending topics with TRENDING/COOLING pills, 4 competitor moves
- **Asset detail modal**: opens from review inbox with Approve / Reject / Revision / ⚡ Generate captions / 📮 Open in Postiz
- **Review queue**: All / Pending / Approved / Rejected filter
- **Killed legacy**: deleted 15 root HTMLs + 11 campaign-os/ HTMLs + 4 .bak files

## What still needs building (PRIORITY ORDER)
1. **Campaign Builder v2** — campaign card currently shows name + status + 1-line brief. Should produce an **extraordinary full plan**: goal, audience, pillars, hook bank, content calendar with day/time/platform per asset, image prompts, captions, KPIs, predicted reach. Currently flat. Treat it as the marketing plan document.
2. **Drag-and-drop calendar** — current is read-only display. Need HTML5 drag-drop to reschedule slots across days, duplicate, color-code by brand, status badges.
3. **Inline caption editor** — current caption studio shows captions as read-only. Need edit-in-place, save to `campaign-data.json`, regenerate single caption without page reload.
4. **Image generation pipeline** — no image gen yet. Need `comfyui` skill flow with strict standards: brand colors, typography, format specs per platform (IG 1080×1080 / 1080×1350 / 1080×1920, GMB 1200×900, etc.), brand guard prompts.
5. **Meme Lord v2** — current memes just dumps `content-ideas.json`. Need: meme format encyclopedia (which memes work, why, when), meme-to-brand fit scoring, format-aware prompts, "this meme is hot right now because…" explainer, golf-aware humour.
6. **Scheduling tool** — `/api/schedule/<assetId>` to push a draft into publish-queue with a target datetime + platform. Connect to the drag-drop calendar.
7. **Marketing trends engine** — `/api/intel/trends_engine` that pulls from `golf-news`, `youtube-trends`, `competitor-tracker`, `reddit-opportunities`, and synthesizes "what's working in marketing THIS WEEK" + "what's new in golf" + "what competitors are doing" with action recommendations.
8. **Campaign full-plan generator** — given campaign name + goal, generate 30 assets across 30 days, hook library, image prompt library, caption library, scheduled to optimal times.

## Architecture (where things live)
```
campaign-os/
  app.py                       # Flask + routes (13 legacy + 4 intel = 17 routes)
  campaign-data.json           # canonical (Do NOT write directly)
  campaign-os.html             # THE SPA (75KB)
  _lib/
    intelligence.py            # 23 view functions (770+ LOC)
    visibility_guard.py        # existing — DO NOT TOUCH (Step 98/99 contract)
    __pycache__/
  tests/
    test_truth_collector.py
data/                          # 167 JSON files (April-May 2026 Phase 1/2 outputs)
```

## Quick-start for next session
```bash
# Server should already be running on 8765. If not:
cd /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard
source .venv/bin/activate
DATA_DIR=/tmp/campaign-os-data PORT=8765 python3 campaign-os/app.py

# Tunnel (for public URL):
cloudflared tunnel --url http://127.0.0.1:8765

# Verify all 23 views:
for r in morning_brief review_inbox calendar trends opportunities performance learning hooks memes billboards caption_studio postiz agents assets hooks_generate captions_generate ctas_generate headlines_generate explain reddit_outreach seo_assistant gbp_suggestions faq_generator trend_catcher; do
  curl -s -o /dev/null -w "%{http_code} /api/intel/$r\n" "http://127.0.0.1:8765/api/intel/$r"
done
```

## Hard rules
- DO NOT publish to Postiz (no API calls to Postiz)
- DO NOT touch `campaign-data.json` directly — use `/api/campaigns` POST or `/api/review/<id>` POST
- DO NOT touch `scripts/_lib/visibility-guard.js` or `campaign-os/_lib/visibility_guard.py`
- DO commit every phase; one commit per logical change
- DO write a status section at the end of every build session (append to this file)

## Roster of files to add
- `campaign-os/_lib/image_gen.py` — image generation pipeline (ComfyUI + brand standards)
- `campaign-os/_lib/meme_lord.py` — meme historian + fit scoring
- `campaign-os/_lib/campaign_planner.py` — full-plan generator
- `campaign-os/_lib/trends_engine.py` — marketing trends synthesizer
- Updates to `campaign-os/campaign-os.html` — drag-drop calendar, inline editor, image prompts panel
- Updates to `campaign-os/app.py` — schedule endpoint, image gen endpoint, plan endpoint

## Build principles
- A feature is **shipped** only when all three exist: backend endpoint (returns real data), front-end section (rendered in the SPA), UX (callable from the cockpit with ≤2 clicks).
- **UX bar**: every screen should feel like software someone would pay for. Fast, alive, minimal clicks, modern. If Christelle wouldn't open it on a Monday morning, it's not done.
- No raw JSON in user-facing UI — every card must render meaningful titles, pills, badges.
- Generators (hooks/captions/headlines/CTAs/images): always have an evergreen fallback so the user never sees an empty page.
- Image gen standards: every prompt must include brand colors (#0a0f1a dark / #34d399 green / #60a5fa blue), typography family, platform format (IG square/portrait/reel, GMB landscape), aspect ratio.
- Meme Lord must be a meme historian: know the format, know why it works, know how to adapt it for a Johannesburg golf brand, score fit 1-10.
- Marketing trends engine must be opinionated: not just "here are signals" but "here's what to do this week because of X".

## Agents you can call for help (delegate_task)
- Code-heavy multi-file work → coding subagent with full context + paths
- Visual / creative work (meme format encyclopedia, image-prompt libraries) → creative subagent
- Research (what's working in marketing this month, golf news synthesis) → research subagent
- Quality review (UX audit, "would I want to use this") → UX-review subagent

## Design tokens (use everywhere)
- Background: #0a0f1a (page), #101727 (card), #172033 (row), #1e2940 (hover)
- Border: #22304d, hover #2a3a5c
- Text: #e6ecf5 (primary), #a8b4cc (secondary), #6c7a96 (muted)
- Accent: #34d399 (primary green), #22c55e (hover), #60a5fa (blue), #a78bfa (purple), #fb923c (orange), #f87171 (red), #facc15 (yellow)
- Gradient: linear-gradient(135deg, #34d399 0%, #60a5fa 100%)
- Radius: 14px (card), 8px (small), 999px (pill)
- Font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif
- Header: 700 weight, -0.02em letter-spacing
- Pill: 10px font, uppercase, 0.04em letter-spacing, 3px 8px padding

## Test baseline (do not break)
- 433 passing / 0 failing / 3 skipped (live-API gated)
- Tests at: `tests/test_*.js`, `campaign-os/tests/test_truth_collector.py`
---

## Cron tick 2026-07-27T20:15 SAST (kickoff — pre-cron)

**Built**:
- Hourly cron job `da7bebf99c66` (12 ticks 22:00–10:00 SAST) for autonomous overnight build
- On-disk status handoff `CAMPAIGN_OS_STATUS.md` with priorities, design tokens, hard rules, agent-call guidance
- Committed working tree (37 files, +2,339 / −21,686) and pushed as `a60ef9a` to `origin/feat/asset-state-engine`
- Fresh public tunnel: `https://episodes-images-futures-coleman.trycloudflare.com` (live, 200)
- Re-stated cron prompt with the new "front-end + back-end + UX = shipped" bar + design tokens + delegate_task guidance

**Files added/modified**: `CAMPAIGN_OS_STATUS.md` (new + appended), staged-and-committed the entire previous-session SPA + intelligence module + 26 stale-UI deletions
**New routes**: none added this tick (all from previous session: 23 /api/intel/<view> + /api/search)
**New UI sections**: none added this tick (kickoff only)
**Tests added**: none this tick
**Commit**: `a60ef9a` + `git push -u origin feat/asset-state-engine` succeeded
**Verified live**: `https://episodes-images-futures-coleman.trycloudflare.com/` → 200; `/api/intel/morning_brief` → 200
**Next priority (PRIORITY 1)**: Campaign Builder v2 — full plan generator (goal/audience/pillars/hooks/calendar/image prompts/captions/KPIs). Backend at `campaign-os/_lib/campaign_planner.py`, frontend cards in `campaign-os.html` "Campaigns" section showing the generated plan for each campaign.
**Blockers**: none
