# Weekly Marketing Report · 2026-08-06 to 2026-08-13

**Brand:** swing-shack

**Window:** 2026-08-06 → 2026-08-13

## Headline
- 21 published, 0 failed, 100.0% win rate.

## Numbers
- **Published:** 21
- **Failed:** 0
- **Win rate:** 100.0
- **Agent runs:** 11
- **Agent pass rate:** 90.9

## Platforms
- **instagram:** 21

## By day
- **Thu:** 21

## Top hooks used
- And we certainly do have spirit 🤣. Visit SwingShack today for all your golfing  (3 uses)
- Book your ball fitting at Swing Shack today. DM us or book online. (3 uses)
- Sub 70 clubs are now available for fitting at Swing Shack. (2 uses)

## Agents
- **approval_captain** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **approval_runner** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **blog_beast** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **brand_guard** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **caption_closer** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **postback_logger** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **publisher** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **qa_inspector** · 1 runs, 0 passed, 0 failed (0.0% pass)
- **reddit_ghost** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **schedule_captain** · 1 runs, 1 passed, 0 failed (100.0% pass)
- **visual_forge** · 1 runs, 1 passed, 0 failed (100.0% pass)

## Week-on-week
- **published:** 21 (prev: 0)
- **failed:** 0 (prev: 0)
- **win_rate_pct:** 100.0% (prev: —)
- **agent_runs:** 11 (prev: 0)

### Sources read (14)
`booking-events.json`, `conversion-attribution.json`, `ga4-attribution.json`, `ga4-metrics.json`, `hook-bank.json`, `ig-analytics.json`, `ig-business-analytics.json`, `post-conversion-score.json`, `reddit-opportunities.json + reddit-replies.json`, `roi-truth.json`, `seo-rankings.json`, `ubersuggest-competitors.json`, `ubersuggest-domain.json`, `youtube-trends.json`

## What's working
- **Win rate is healthy at 100.0%.** _(category: publishing, source: `published-items.json`)_
  - 21 published, 0 failed this week (threshold: ≥80% = good).
- **Top hook 'And we certainly do have spirit 🤣. Visit SwingShack today fo…' is being reused (3×).** _(category: voice, source: `hook-bank.json`)_
  - Reuse = the system trusts it. Worth reading why it works in hook-bank.md.
- **Agent fleet pass rate is 90.9%.** _(category: fleet, source: `agent-runs.json`)_
  - 10/11 runs passed across 11 agents.
- **Instagram is the dominant publish channel (21 posts).** _(category: channels, source: `published-items.json`)_
  - Consider replicating winning formats to underused channels.
- **Thu is your strongest publish day this week.** _(category: cadence, source: `published-items.json`)_
  - 21 posts went out on that day.
- **GA4 recorded 880 website sessions; google is your top acquisition channel (541 sessions).** _(category: web_traffic, source: `ga4-metrics.json`)_
  - Source breakdown from ga4-metrics.json across 5 sources. Last fetch: 2026-08-13T11:18:53.950Z.
- **SEO domain snapshot — organic traffic = 967; organic keywords = 51; domain authority = 13; backlinks = 24; referring domains = 9.** _(category: seo, source: `ubersuggest-domain.json`)_
  - ubersuggest-domain.json via daily fetch_ubersuggest.py cron. Last fetch: 2026-08-10. Pulled from `swingshack.co.za` `domain_overview` + `backlinks_overview` MCP tools.
- **Conversion truth band - Publishing ROI is STRONG_PROXY. Lead and ad ROI is UNMEASURABLE. Only DIRECT comes when GA4 → booking system integrates.. Last engine run: 2026-08-13.** _(category: attribution, source: `roi-truth.json`)_
  - roi-truth.json reclassifies every revenue source (publishing, lead routing, ad budget, etc.) into a confidence band based on whether the GA4 booking confirmation event is live. DIRECT = booking-confirmed; STRONG_PROXY = UTM chain + session trackable; WEAK_PROXY = indirect correlation only; UNMEASURABLE = no data path.
- **Top attribution unblocker - WhatsApp Business API + CRM → booking system integration; Meta Ads API + GA4 goal tracking + ROAS calculation. Closing either lifts the affected sources from unmeasurable to verified revenue.** _(category: attribution, source: `roi-truth.json`)_
  - roi-truth.json recommendations (priority 1). These are the two highest-leverage integrations that would convert the current UNMEASURABLE / WEAK_PROXY sources into DIRECT (booking-confirmed) attribution. Each recommendation cites the specific API + tracking event that closes the loop.
- **GA4 booking events - 2 of 6 measurable. Priority-1 events not yet tracking: booking_completed.** _(category: attribution, source: `booking-events.json`)_
  - booking-events.json inventory. These are the specific GA4 events that need to be instrumented on the booking funnel (form_submit, booking_completed, service_selected) to convert the conversion-truth band from STRONG_PROXY to DIRECT (verified revenue).
- **Booking funnel volume - 291 sessions to high-intent pages in the last 7d. Top entry: /bookings/.** _(category: attribution, source: `conversion-attribution.json`)_
  - conversion-attribution.json joins GA4 page traffic with IG content engagement. 291 sessions hit pages matching booking/fitting/contact patterns. This is the live conversion-funnel volume - the number every post should ultimately be measured against.
- **Top converting CTA type - BOOKING: 2.68% avg engagement across 12 posts. More effective than 3 other CTA buckets.** _(category: attribution, source: `conversion-attribution.json`)_
  - conversion-attribution.json cta_performance[]. Captions bucketed by keyword (BOOKING/LESSONS/FITTING/PROMO/ENGAGEMENT/SOFT) then ranked by avg engagement rate. The top bucket is what the content engine should default to for max IG engagement.
- **Top service by content engagement - Club Fitting: 3.01% avg engagement, 2,326 reach across 12 posts in window.** _(category: attribution, source: `conversion-attribution.json`)_
  - conversion-attribution.json service_correlation[]. Posts matched to Golf Lessons/Club Fitting/Simulator/Membership/Events by caption keywords. Club Fitting is the leader - the content engine should weight this service higher when picking the next post topic.
- **Top hook theme - TrackMan / Stats: 3.60% avg engagement across 3 posts.** _(category: attribution, source: `conversion-attribution.json`)_
  - conversion-attribution.json hook_themes[]. Posts matched to themes by caption keywords (TrackMan/Slice Fix/Lessons/Putting/Fitting/Contest/Membership/Simulator). TrackMan / Stats is the highest-converting angle.
- **Booking completion volume - 58 sessions reached the booking confirmation page in the last 30d (17.5% browse-to-complete conversion). 31 unique completion URLs captured.** _(category: attribution, source: `ga4-attribution.json`)_
  - ga4-attribution.json booking_completion_proxy. Detects /bookings/?facilityId=&serviceId=&clientEmail=&packageRedeem= URLs (Amelia booking plugin populates these on submit). This is a HIGH-CONFIDENCE proxy for actual bookings until the booking_completed GA4 event is instrumented on the live site.
- **Top booking-completion channel - clublab.app: 44 booking completions in 30d (76% of total). Breakdown: clublab.app=44, (direct)=10, google=2, (not set)=1, c.yoco.com=1.** _(category: attribution, source: `ga4-attribution.json`)_
  - ga4-attribution.json booking_completion_proxy.completions_by_source. These are real booking-confirmation page sessions (with clientEmail + serviceId in URL), not just traffic. Shows which acquisition channel actually closes bookings vs which only drives awareness.
- **IG post attribution - 48 /bookings/ + /club-fitting/ sessions tagged with IG UTM content in 30d. Top UTM-content: 'trackman-authority-961989' drove 14 sessions. 0/8 attribution rows matched to specific IG posts (others are legacy campaign tags).** _(category: attribution, source: `ga4-attribution.json`)_
  - ga4-attribution.json instagram_post_attribution. Pulled from GA4 (sessionSource=instagram, pagePath contains /bookings/ or /club-fitting/), grouped by sessionManualAdContent (the hook_id). Mismatch with ig-business-analytics.json hook_ids is a known gap: GA4 captured legacy UTM tags (hook-beginner, trackman-authority-961989) while newer posts use caption-derived hook_ids. Backfill the UTM scheme or accept the gap - either is fine, but be explicit.
- **Best converting post: 2026-07-25 (image). Reach 178, 1.12% engagement, +267% /bookings/ lift vs baseline. Score 100/100. Caption: "Off-the-rack is fine for groceries.
For clubs, let’s aim a little higher.
Book y". Themes: club_fitting, golf_humor, booking_cta.** _(category: content_performance, source: `post-conversion-score.json`)_
  - post-conversion-score.json ranks every IG post by its contribution to /bookings/ traffic. Score formula combines direct hook_id attribution (10x), time-window D+0/+1/+2 IG /bookings/ sessions (3x), reach (0.001x), and a 1.5x multiplier for historically winning theme combos (club_fitting + booking_cta). Lift % compares to the median IG /bookings/ traffic in the 30d window. Format: image, checked across all media types (reels vs images) in the top 10.
- **Format winner: image. Reels (6 total) avg score 43.6, images (10 total) avg score 77.4 in the top 10. Images convert better per post.** _(category: content_strategy, source: `post-conversion-score.json`)_
  - Computed from post-conversion-score.json posts_ranked top 10. Reels typically get higher reach but lower per-post conversion. Images in our top 10 converted at higher per-post scores. Both formats drive /bookings/ lift. Choose by content type, not format alone.
- **Next-post recommendation: Combine these themes for max /bookings/ conversion: booking_cta, club_fitting, wrong_ball. Suggested format: image. Example angles: 'Off-the-rack is fine for groceries.
For clubs, let’s aim a little higher.
Book y; Wrong ball? Let’s fix it. 

Book your ball fitting today!'.** _(category: content_strategy, source: `post-conversion-score.json`)_
  - post-conversion-score.json recommendation block. Built by counting theme frequency in the top 5 scoring posts, plus comparing reels vs images avg score in the top 10. The top 5 historically lifted /bookings/ traffic by 50-300% over baseline. The content engine should weight this combination when picking the next post idea.
- **YouTube trends pulled; active themes this week: trackman, slice_fix, practice, indoor, lessons.** _(category: youtube_trends, source: `youtube-trends.json`)_
  - From youtube-trends.json trending_themes (5/8 themes active) + 10 candidate videos fetched.
- **All 5 Reddit opportunity threads have drafted ghost replies (5 drafts).** _(category: reddit_outreach, source: `reddit-opportunities.json + reddit-replies.json`)_
  - 5 drafts in reddit-replies.json vs 5 opportunities in reddit-opportunities.json. ready_for_qa: opp=5, reply=5.
- **IG account reached 25,565 unique accounts in the last 30d.** _(category: ig_engagement, source: `ig-business-analytics.json`)_
  - From ig-business-analytics.json window_totals.reach (25565); accounts_engaged=169, total_interactions=372. This is the live Graph API number. ig-analytics.json's reach field stays 0 because the legacy sync doesn't populate it.
- **30d IG account engagement rate is 0.66%.** _(category: ig_engagement, source: `ig-business-analytics.json`)_
  - accounts_engaged=169 / reach=25565. Industry baseline for indoor-golf niche is ~2-5%; anything above 5% is strong signal of an audience that returns.
- **Top IG post in window reached 1,400 accounts with 20 interactions.** _(category: ig_engagement, source: `ig-business-analytics.json`)_
  - Caption hook: "Tired of the same old setup 🥱 try Avoda today! ". Permalink: https://www.instagram.com/reel/DbVgJmCMZZC/. From ig-business-analytics.json top_post.

## What's not working
- • **5 agent(s) didn't run this week: copywriter, retina, forge, imagegen, scout.** _(severity: low, source: `agent-runs.json`)_
  - Either nothing to do (fine) or a missed opportunity.
- ⚠️ **10 SEO keywords tracked but zero have rank data — rankings fetcher is offline.** _(severity: medium, source: `seo-rankings.json`)_
  - seo-rankings.json has 10 keywords, all current_rank: null. Need a live rank fetcher (Ubersuggest MCP wired). Last update: 2026-08-13T11:14:03.371Z.
- ⚠️ **Strongest organic competitor: worldofgolf.co.za — 52 shared keywords, DA 26 (us: 13).** _(severity: medium, source: `ubersuggest-competitors.json`)_
  - ubersuggest-competitors.json via fetch_ubersuggest.py. Top of list by commonKeywordCount. Gap keywords (we don't rank but they do): 300. Last fetch: 2026-08-10.
- 🛑 **Daily IG reach has fallen 62% over the past 15d (vs the prior 15d).** _(severity: high, source: `ig-business-analytics.json`)_
  - From ig-business-analytics.json daily_reach: prior 15d avg=1237, recent 15d avg=467. Reach contraction is the earliest signal of an audience that the algorithm has stopped pushing.

## Look at
- ? **Only publishing to instagram this week.** _(source: `published-items.json`)_
  - Cross-posting earned media — visualizer works for Facebook too. Worth 30 min of experiment.
- ? **IG has 10 posts tracked but zero reach recorded.** _(source: `ig-analytics.json`)_
  - Reach counter is 0 across all posts. Either engagement metrics haven't synced, or the sync ran before the IG API returned metrics. Re-run sync_ig_analytics.js to verify.
- ? **Hook-ID overlap between published-items and IG is 3 (0 expected signal).** _(source: `ig-analytics.json + published-items.json`)_
  - in_pub_not_ig=0, in_ig_not_pub=7. Either the sync is showing different content from what was published, or hook_ids aren't linking between sources.
- ? **2 revenue source(s) still unmeasurable - Lead Routing, Budget Shifts. We are publishing and spending on these without being able to attribute any revenue to them.** _(source: `roi-truth.json`)_
  - roi-truth.json sources[] filtered by can_measure='UNMEASURABLE'. Until the recommended integrations land (WhatsApp Business, Meta Ads + GA4 goal tracking, GA4 booking confirmation event), these channels are operating blind.
- ? **GA4 booking_completed event is NOT being tracked. Amelia events are firing (form_view, checkout_view) but the confirmation page is not pushing booking_completed. Until this lands, all booking-revenue attribution is a proxy based on URL pattern, not event-tracked.** _(source: `ga4-attribution.json`)_
  - ga4-attribution.json events_tracked. Top events: page_view:5325, user_engagement:3802, session_start:3206, first_visit:2169, tel:12. Wiring the booking_completed event is a 1-2h code change on the Amelia booking confirmation page and would upgrade 3 channels from STRONG_PROXY to VERIFIED_REVENUE in the conversion truth band.
- ? **Lowest-converting posts (bottom 3 of 16) share themes booking_cta, golf_humor, club_fitting, golf_lessons. These patterns are NOT driving /bookings/ traffic - consider rotating them out of the next-post rotation.** _(source: `post-conversion-score.json`)_
  - post-conversion-score.json bottom 3 of 16 ranked posts. Lowest scores correlate with these themes. The content engine should deprioritise these in next-post selection.
- ? **@swingshack has 2,490 IG followers as of this fetch.** _(source: `ig-business-analytics.json`)_
  - From ig-business-analytics.json account.followers_count. Compare against next fetch to detect follower-delta direction.

> **Headline take:** Win rate is healthy at 100.0%.

## Data sources powering this report
- **Instagram (`ig-analytics.json`)** — 10 posts · reach=0 · likes=64 · saves=0 · shares=0 · comments=1
  - hook_id overlap with published: 3; in published but not in IG: 0; in IG but not published: 7
- **GA4 (`ga4-metrics.json`)** — 880 sessions · top source: **google** (541 sessions) · 5 sources tracked · fetched: 2026-08-13
- **YouTube trends (`youtube-trends.json`)** — 19 videos found · top 10 · active themes: trackman, slice_fix, practice, indoor, lessons
- **Reddit (`reddit-opportunities.json + reddit-replies.json`)** — 5 opportunities · 5 drafted replies · ready_for_qa (opps: 5, replies: 5) · subs: r/golf=3, r/golftips=1, r/Johannesburg=1
- **SEO (`seo-rankings.json`)** — 10 keywords · 0 have rank data · rising=0 falling=0 · freshness: 2026-08-13 ⚠️ fetcher offline
- **Hook bank (`hook-bank.json`)** — proven_and_trending=0 · proven_only=3 · trending_to_test=0 · retire=5
  - ⚠️ **hook-bank mismatch:** 0 of published hook_ids are NOT in hook-bank (8 bank entries). Bank regenerated independently of publish history.

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
- **Primary:** equipment · **mix:** equipment (8), coaching (6), general (5), trackman (2)
  - _equipment_ (8): 'YOUR CLUBS ARE HOLDING YOU BACK

🎮 Practice

Link in bio · Book your session

#I…' / 'Book your ball fitting at Swing Shack today. DM us or book o

🏌️ Club Fitting

S…'
  - _coaching_ (6): 'THAT SLICE COSTING YOU YARDS?

🎮 Practice

Link in bio · Book your session

#Ind…' / 'Coach Catherine explains a common swing flaw

🎮 Practice

Drop a 🫂 below

#Indoo…'
  - _general_ (5): 'POV: First time at Swing Shack

Swing Shack
Link in bio · Book your session…' / 'YOUR GOLF NEEDS A MENTOR

Swing Shack
Link in bio · Book your session…'
