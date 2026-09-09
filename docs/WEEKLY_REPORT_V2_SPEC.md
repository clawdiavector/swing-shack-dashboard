# Weekly Report v2 Spec (2026-08-14)

Rebuild Swing Shack `/weekly-report?brand=X` page to match the Stick reference
template (per Christelle's screenshots). Goals:

1. **Hero with interpretive headline** (not "Weekly Marketing Report" label)
2. **5-bullet TL;DR with bolded insight + context sentence**
3. **Comparison table** with Facebook Stories + Instagram Stories rows
4. **Per-platform sections** with full table + Strong/Watch boxes
5. **Content earning attention** with per-platform bullets + direction strip
6. **Google Ads this week** cards (Spend/Impressions/Clicks/Local actions)
7. **Working / Needs attention** with bold lead-ins + context sentences
8. **This week's focus** = 6 concrete actions
9. **Honest no-data display** distinguishes "0 = no data source" from "0 = real zero"
10. **Footer** explains source windows

## Reference (Stick)

- Eyebrow: "STICK • WEEKLY MARKETING REPORT • 7 AUG 2026"
- Hero h1: "Traffic is converting into conversation." (interpretive)
- Subtitle: plain-English summary of the week's story
- Focus pills: 5 brand pillars as chips
- TL;DR bullets: 5 takeaways with bolded insight + context sentence
- KPI cards: Content / FB reach / IG reach / New contacts
- Comparison table: 8 rows (Content, FB reach, IG reach, New contacts, FB posts,
  FB Stories, IG posts, IG Stories)
- Each table gets "Read:" callout with plain-English interpretation
- Facebook section: full table + Strong box + Watch box
- Instagram section: full table + Read box
- Content earning attention: per-platform bullets + Content direction strip
- Website and acquisition: GA4 cards + table + Read
- Google Ads this week: Spend/Impressions/Clicks/Local actions cards
- What is working: bulleted with bold lead-ins
- What needs attention: bulleted with bold + context
- This week's focus: 6 concrete actions
- Footer: source window explanation

## What we ship now (Swing Shack)

Currently has: TL;DR (2 bullets), KPI cards (Content/GA4/IG/Review),
Comparison table (7 rows), Facebook section (placeholder when no Meta),
Instagram section, GA4 section, Generic Working/Attention/Focus lists,
Footer with snapshot info.

## The fix — three layers

### Layer 1: Honest no-data display

When a metric source is dead (e.g. Meta not configured), don't render "0".
Instead:
- Show "—" in the value column
- Show "(Meta not connected)" in the change column (neutral color)
- This distinguishes "we don't measure this" from "actually zero"

Affected rows: Facebook reach, Facebook interactions, New contacts (if no lead
source wired), Review queue depth (only if no approval-queue.json exists).

### Layer 2: Hero + TL;DR upgrade

- Hero h1: derived from best positive delta + worst negative delta. e.g.
  "Reach cooled, but conversations doubled." or "Cadence held; IG quality
  improved." Falls back to "Weekly review for {brand}" when no delta is large
  enough.
- Subtitle: plain-English summary from same logic
- TL;DR: always 5 bullets with bolded lead + context sentence:
  1. Reach status (FB + IG + delta vs prev)
  2. Strongest acquisition engine
  3. Engagement quality signal (interactions/follows/response rate)
  4. Website traffic + paid vs organic
  5. Pipeline flag (reviews/drafts/conversions)

### Layer 3: Per-platform + Google Ads sections

- Facebook: only show if Meta configured. Otherwise show "Meta not connected"
  panel (current behaviour is fine).
- Instagram: full table + Read box (already there, polish)
- Google Ads: only show if Google Ads configured. Otherwise "Google Ads not
  connected" panel.

### Layer 4: Stories + Posts rows in comparison table

- Add Facebook posts + Facebook Stories + Instagram posts + Instagram Stories
  rows to the comparison table
- These come from Meta Graph when configured, or from data/ig-analytics.json
  for IG posts when offline

### Layer 5: This week's focus

- 6 concrete actions derived from working[]/attention[] deltas
- Each action is bold-led + context-rich (e.g. "Keep free club assessment
  content visible and easy to book. The conversion path that worked last
  cycle still works — don't change the offer.")

## Implementation outline

1. `_weekly_compute_metrics()` — add fb_posts, fb_stories, ig_posts,
   ig_stories, response_rate, paid_dep_pct, paid_vs_organic to the dict
2. `_weekly_collect_current()` — read these from Meta when configured, else
   from cached data/ files; mark "not configured" reason for honesty
3. `_weekly_render_html()` — rebuild hero, TL;DR, comparison, sections,
   focus to match Stick layout
4. `_weekly_render_markdown()` — mirror HTML structure in MD
5. Tests — verify hero text, TL;DR bullets, table rows, source-status
   honesty

## What I will NOT do in this session

- Stories fetcher for IG/FB (separate session — needs new fetcher + 28d story metrics endpoint)
- Lead-source wiring (no lead source is currently wired; New contacts will show "—")
- Google Ads connector (separate session)
- Voice/narrative generation (Stick ref shows hand-written; we will use rules-based)

## Time budget

~45 min for full rebuild + tests + push.
