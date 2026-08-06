# Weekly Marketing Report · 2026-07-30 to 2026-08-06

**Brand:** swing-shack

**Window:** 2026-07-21 → 2026-07-22 (last active publish window before pause · 15d ago)

> ⚠️ **Pipeline in rest-mode: no publishes in the last 7 days. Showing last active publish window (57 posts, 2026-07-21 → 2026-07-22). Approve an active campaign or restart the cron to refresh.**

## Headline
- 57 published (last active window 2026-07-21), 0 failed, 100.0% win rate. Pipeline paused since 2026-07-21 — this is your most-recent live snapshot.

## Numbers
- **Published:** 57
- **Failed:** 0
- **Win rate:** 100.0
- **Agent runs:** 0
- **Agent pass rate:** —

## Platforms
- **instagram:** 57

## By day
- **Tue:** 57

## Top hooks used
- that-slice-costing-you-yards-off-the-tee--trackman (3 uses)
- need-to-relax-and-find-your-golf-swing-tempo--join (3 uses)
- go-to-your-coaching-sessions--your-ball-deserves-b (3 uses)
- improve-your-game-with-the-coaches-tip-of-the-day- (3 uses)
- swingshack-merch-coming-in-hot--- (3 uses)

## Week-on-week
- **published:** 57 (prev: 0)
- **failed:** 0 (prev: 0)
- **win_rate_pct:** 100.0% (prev: —)
- **agent_runs:** 0 (prev: 0)

### Sources read (6)
`ga4-metrics.json`, `hook-bank.json`, `ig-analytics.json`, `reddit-opportunities.json + reddit-replies.json`, `seo-rankings.json`, `youtube-trends.json`

## What's working
- **Win rate is healthy at 100.0%.** _(category: publishing, source: `published-items.json`)_
  - 57 published, 0 failed this week (threshold: ≥80% = good).
- **Instagram is the dominant publish channel (57 posts).** _(category: channels, source: `published-items.json`)_
  - Consider replicating winning formats to underused channels.
- **Tue is your strongest publish day this week.** _(category: cadence, source: `published-items.json`)_
  - 57 posts went out on that day.
- **GA4 recorded 1,008 website sessions; google is your top acquisition channel (396 sessions).** _(category: web_traffic, source: `ga4-metrics.json`)_
  - Source breakdown from ga4-metrics.json across 5 sources. Last fetch: 2026-08-06T09:03:26.066Z.
- **YouTube trends pulled; active themes this week: trackman, slice_fix, practice, indoor, lessons.** _(category: youtube_trends, source: `youtube-trends.json`)_
  - From youtube-trends.json trending_themes (5/8 themes active) + 10 candidate videos fetched.
- **All 5 Reddit opportunity threads have drafted ghost replies (5 drafts).** _(category: reddit_outreach, source: `reddit-opportunities.json + reddit-replies.json`)_
  - 5 drafts in reddit-replies.json vs 5 opportunities in reddit-opportunities.json. ready_for_qa: opp=5, reply=5.
- **2 IG-proven hooks aren't being used in publishing this week.** _(category: voice, source: `hook-bank.json + published-items.json`)_
  - Cross-cut: hook-bank.json output_buckets.proven_only (2 hooks) vs published-items.json linked_hook_ids (17 of those not in IG analytics). Opportunity to rotate them in.

## What's not working
- ⚠️ **10 SEO keywords tracked but zero have rank data — rankings fetcher is offline.** _(severity: medium, source: `seo-rankings.json`)_
  - seo-rankings.json has 10 keywords, all current_rank: null. Need a live rank fetcher (Ubersuggest MCP wired). Last update: 2026-04-22T06:31:00.312Z.
- • **17 of your published hook_ids aren't in the hook-bank at all.** _(severity: low, source: `published-items.json + hook-bank.json`)_
  - published-items.json has unique hook_ids in use, hook-bank.json only contains 8 entries (across all buckets). Hook-bank has been regenerated independently and lost the published history.

## Look at
- ? **Only publishing to instagram this week.** _(source: `published-items.json`)_
  - Cross-posting earned media — visualizer works for Facebook too. Worth 30 min of experiment.
- ? **IG has 10 posts tracked but zero reach recorded.** _(source: `ig-analytics.json`)_
  - Reach counter is 0 across all posts. Either engagement metrics haven't synced, or the sync ran before the IG API returned metrics. Re-run sync_ig_analytics.js to verify.
- ? **Hook-ID overlap between published-items and IG is 0 (0 expected signal).** _(source: `ig-analytics.json + published-items.json`)_
  - in_pub_not_ig=17, in_ig_not_pub=10. Either the sync is showing different content from what was published, or hook_ids aren't linking between sources.

> **Headline take:** Win rate is healthy at 100.0%.

## Data sources powering this report
- **Instagram (`ig-analytics.json`)** — 10 posts · reach=0 · likes=49 · saves=0 · shares=0 · comments=1
  - hook_id overlap with published: 0; in published but not in IG: 17; in IG but not published: 10
- **GA4 (`ga4-metrics.json`)** — 1,008 sessions · top source: **google** (396 sessions) · 5 sources tracked · fetched: 2026-08-06
- **YouTube trends (`youtube-trends.json`)** — 19 videos found · top 10 · active themes: trackman, slice_fix, practice, indoor, lessons
- **Reddit (`reddit-opportunities.json + reddit-replies.json`)** — 5 opportunities · 5 drafted replies · ready_for_qa (opps: 5, replies: 5) · subs: r/golf=3, r/golftips=1, r/Johannesburg=1
- **SEO (`seo-rankings.json`)** — 10 keywords · 0 have rank data · rising=0 falling=0 · freshness: 2026-04-22 ⚠️ fetcher offline
- **Hook bank (`hook-bank.json`)** — proven_and_trending=0 · proven_only=2 · trending_to_test=1 · retire=5
  - ⚠️ **hook-bank mismatch:** 17 of published hook_ids are NOT in hook-bank (8 bank entries). Bank regenerated independently of publish history.

## Visual insights (brand image corpus · 122 images)
- **Luminance:** dark: 72, mid: 42, unknown: 8
- **Top palettes:** `#F8F8F8` (323%) · `#060808` (306%) · `#3A3A3A` (283%) · `#070909` (176%) · `#000000` (145%)
- **Moods:** calm (96) · professional (96) · luxurious (42) · neutral (18) · clean (8)
- **Subjects:** text-overlay (111) · product (50) · minimal (8)
- **Brand mentions:** GTS Putter (18) · Vice (9) · Mileseey (5) · Vessel Bag (4) · Vessel (4)
- **Brand-canon compliance pass rate:** 48.4%

### Visual insights to act on
- **59% of approved imagery is dark-luminance.** _(category: palette)_
  - Out of 122 images: dark=72, mid=42, bright=0. Correlate with weekly published-posts to see if dark posts drive more engagement than non-dark.
- **Most-cited mood is 'calm' (96× across corpus).** _(category: mood)_
  - Two-cardinality check: confirm posts with this mood outperform 'general' mood posts in weekly engagement.
- **Most images cluster in the 0.8 brand-compliance bucket.** _(category: compliance)_
  - 22/122 images. Pull this bucket for Quick Wins — those are the visual recipes that already match canon.
- **Visual-brand compliance pass rate is 48.4% across 122 images.** _(category: compliance)_
  - Aim for 75%+ canon-alignment before scaling output. Use the failing images' dominant_hex + composition_tags as a corrective reference.
- **Object 'text-overlay' dominates 91% of approved images.** _(category: variety)_
  - Consider whether over-representation is diluting variety. Add an object-type in the next brief if visual monotony is a risk.
- **Brand 'GTS Putter' appears across 18 approved images.** _(category: subjects)_
  - Tells you which SKUs are photographable already. The dark-count of any other brand = a content gap.

## IG topic mix this week
- **Primary:** coaching · **mix:** coaching (36), general (14), equipment (7)
  - _coaching_ (36): 'Need to relax and find your golf swing tempo? Join Coach Cat

🎯 Coaching

DM us …' / 'Go to your coaching sessions. Your ball deserves better 🫂

🎯 Coaching

Swipe up …'
  - _general_ (14): 'SwingShack merch coming in hot 🔥

Swing Shack
Link in bio · Book your session

#…' / 'Sometimes u just need a bit of tough love 😅🤣

Swing Shack
Link in bio · Book you…'
  - _equipment_ (7): 'That slice costing you yards off the tee? TrackMan found it 

🏌️ Club Fitting

L…' / 'Want to win a fully custom built driver?👀

🏌️ Club Fitting

Swipe up · Learn mor…'
