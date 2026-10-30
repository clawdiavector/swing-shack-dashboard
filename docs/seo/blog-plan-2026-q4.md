# Swing Shack blog plan, Q4 2026 (SEO and GEO)

Written 2026-10-27. Status: **proposed, needs Christelle's yes on the cadence.**
Evidence and caveats: wiki `research/blog-cadence-seo-geo-evidence-2026-10-27`.

## The decision
**Not one blog a day. Two a week for eight weeks, then one a week, plus a refresh of two old posts a month.** Daily presence comes from the things that can honestly be daily: the Google Business post queue (one a day at 09:00 SAST) and social. Each blog feeds three to five of those.

## Why not daily
- **Frequency is not a ranking factor.** Google's John Mueller said its algorithms do not take posting frequency into account, as reported by [Search Engine Journal](https://www.searchenginejournal.com/how-freshness-works/457485/). More posts can get a site crawled more often; that is not the same as ranking better.
- **Volume without value is the thing Google penalises.** Its spam policy on [scaled content abuse](https://developers.google.com/search/docs/essentials/spam-policies) covers many pages made mainly to rank, however they are made. Google's [helpful content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content) calls generative AI text produced without manual oversight low effort.
- **Quality features are what move AI answers.** In the original [GEO study](https://arxiv.org/abs/2311.09735), adding sources, quotations and statistics raised visibility roughly 30 to 40% on the paper's measures in its test engine, and keyword stuffing did not help. Lower-ranked sites gained most, which is Swing Shack's position.
- **The real limit is facts and review, not typing.** Every post needs something only Swing Shack has (real TrackMan sessions, a coach's words, real photos, current prices) and a person's review. Two a week is about what that supports.

## What matters more than post count
Whitespark's 2026 [local ranking factors survey](https://whitespark.ca/local-search-ranking-factors/) (47 local SEO experts, scores not Google weights) puts these at the top for **AI search visibility**: presence on expert "best of" lists (rank 1), a **dedicated page for each service** (rank 2), authority of mentions in news, blogs and associations (rank 4), geographic relevance of content (rank 6). So in parallel with the posts:
1. **Service pages first.** Coaching, Club Fitting, Free assessment and Membership each need a strong dedicated page. The daily GEO audit already flags four pages with no clear Q&A blocks.
2. **Third-party mentions.** The backlink list (`docs/seo/backlink-targets.md`) is as important as blog volume.
3. **Google Business Profile.** Ranks highest for the map pack; keep reviews coming and the information consistent.

## Standard for every post (the checklist)
1. **Answer first.** A short, direct answer near the top.
2. **Something only we have.** Real, anonymised TrackMan numbers from sessions (with the player's OK), or a named coach's view. This is the information gain Google asks about.
3. **Sourced figures and quotes.** At least two numbers or quotations, each with a link to its source. No link, no number. Prices come from the booking page and carry its link.
4. **A named author.** A coach byline, linked to who they are. Google asks for clear authorship, and to say how the content was made where readers might ask. Decision for Christelle: add a one-line note such as "Written with Swing Shack's coaches and checked by [name]".
5. **A visible Q&A section** (the audit flags its absence). Google says no special markup is needed to appear in [AI Overviews](https://developers.google.com/search/docs/appearance/ai-features).
6. **Links:** to the matching service page and to booking. Real photos, never renders.
7. **Voice rules:** no em dashes, no unsourced claims, Swing Shack only.
8. **After publishing:** request indexing in Search Console and add the post to the GEO watchlist.

## Timing
No study I found shows that publish day or hour affects rankings or indexing. The sources that exist measure social shares from 2011. So: **Tuesday and Thursday mornings (SAST)**, because a steady rhythm is easy to keep and lines up with social posting. Check Search Console after eight weeks and move it if your own data says so.

Freshness helps where the topic is time-sensitive (seasonal, prices, "best of"). An [Ahrefs study](https://ahrefs.com/blog/do-ai-assistants-prefer-to-cite-fresh-content/) of 17 million citations found AI assistants cite newer pages than Google's organic results do, and ChatGPT most of all. It is correlation. Refresh with real changes and show the updated date. Changing a date alone is called out by Google as a trick.

## Calendar (targets, in order)
Keyword volumes are Ubersuggest and worldwide, not South African; treat them as relative.

| Week | Tue | Thu | Notes |
|---|---|---|---|
| 1 | | **Golf lessons in Johannesburg** (staged, post 4204) | Needs a real lesson photo. Targets "golf lessons" (480, not ranking). |
| 2 | **Indoor golf in Johannesburg** (staged, 4206) | **TrackMan numbers explained** (staged, 4205) | TrackMan needs a coach read first. "Indoor golf" ranks 3. |
| 3 | **Club fitting in Johannesburg: what happens, how long, what it costs** | **The free 30-minute club assessment: what it covers** | Prices and free assessment read from the booking page, with link. "How long does club fitting take". |
| 4 | **Mallet vs blade putter: which suits your stroke** | **How accurate is a golf simulator?** | Putter piece needs a fitter's quote. "Mallet putter vs blade" is the biggest informational term in the cache (6,600). "Simulated golf" ranks 4 (2,400). |
| 5 | **Is indoor golf worth it?** | **How often should you regrip your clubs?** | Question-style posts suit AI answers. |
| 6 | **Rain, heat and load shedding: practising year round in Johannesburg** | **Golf gifts for him in South Africa** | Seasonal, before December. Only list items we can source and link. |
| 7 | Refresh: Vice golf balls | Refresh: Takomo irons | Add first-party facts, sources, a visible updated date. |
| 8 | **Swing analysis in Johannesburg: what you get from a TrackMan session** | Review: Search Console after eight weeks, then drop to one a week | |

Black Friday and Christmas offers are held until Herman approves them.

## Measure
- Search Console, per post: impressions, clicks, queries (AI Overview clicks count under Web).
- Google Business Profile: calls, direction requests, bookings.
- GEO watchlist: how often Swing Shack is named for a fixed set of questions. The runner is built but **not scheduled** (`schedule_enabled: False`, needs `OPENAI_API_KEY`). Turning it on weekly is the missing piece for measuring GEO.
- Keep or kill: after eight weeks, keep the post types that gained impressions and bookings, and stop the rest.

## Who does what
- **Claude:** drafts from real facts, sources the figures, converts to WordPress drafts, sets Yoast fields, runs the checks.
- **Christelle:** approves each draft in Review, supplies photos.
- **Coach:** one short quote or data point per post, and one read of the TrackMan piece.
- **Jason or WordPress admin:** installs the Yoast pages snippet (see `wordpress-yoast-pages-snippet.md`).
