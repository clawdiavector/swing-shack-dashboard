# Stick blog and SEO plan, Q4 2026

Written 2026-10-28. Status: **approved in outline by Christelle ("all of it"), details open.**
Same evidence as the Swing Shack plan (`blog-plan-2026-q4.md`, wiki `research/blog-cadence-seo-geo-evidence-2026-10-27`). Stick is a separate company: Stick text names Stick only, in Stick's own voice.

## Where Stick stands (2026-10-28)
- Domain authority 3, 7 backlinks from 1 domain (Ubersuggest, `data/ubersuggest-domain-stick.json`). Swing Shack, for comparison: 12, 15 domains.
- Of the tracked keywords, only "vice golf balls south africa" ranks (9). The tracked set is mostly retail: "pro shop somerset west" (590), "golf apparel south africa" (320), "takomo irons south africa" (260). Volumes are Ubersuggest and worldwide.
- 11 blog posts (April to June 2026), all about fitting. Several point at the golfer and use unsourced numbers (for example "why your driver loft is wrong and why it costs you 20 yards").
- The homepage, Club Fitting and Coaching pages share one search description.
- Real pages: `/club-fitting-at-stick`, `/coaching-at-stick`, and brand pages (`/takomo-at-stick`, `/psycho-bunny-at-stick`, `/l-a-b-golf-at-stick`, `/vice-golf-at-stick`, `/avoda-at-stick`, `/miura-at-stick`, `/fujimoto-at-stick`).
- The daily GEO check covers Stick (4 questions a day).
- Yoast on stickgolf.co.za has the same limit as Swing Shack: page titles and descriptions are not writable over REST until the snippet is installed (Jason emailed 2026-10-28).

## The decision
**One new post a week, plus two refreshes of old posts a month.** Not more, because Stick's gains come first from the basics:
1. **Google Business Profile** (map pack) and consistent name, address and phone.
2. **Mentions on other sites** (Whitespark's AI-visibility top factors: "best of" lists, mentions in news, blogs and associations). With one referring domain, every real mention counts.
3. **Dedicated pages per service and per brand** (already there; give each its own search description and a visible Q&A).
4. **Product and category pages** for retail searches, once the Shopify store opens.

## Refresh first (two a month)
Rewrite the old posts to the house rules: no unsourced numbers, pressure on the equipment not the golfer, a named author, real photos, sources linked, a visible updated date. Order: driver loft, wedges, off-the-rack, irons left or right, then the rest.

## New posts (one a week, Thursdays)
| Week | Post | Why |
|---|---|---|
| 1 | Club fitting in Paarl: what happens, how long it takes, what it costs | Service and place; prices from the booking page, with link |
| 2 | Takomo irons in South Africa: fitting them at Stick | "takomo irons south africa" (260), Stick stocks Takomo |
| 3 | Psycho Bunny golf apparel at Stick | "golf apparel south africa" (320); links to `/psycho-bunny-at-stick` |
| 4 | Golf gifts in South Africa | Seasonal, before December; only stocked, linked items |
| 5 | The free 30-minute club assessment at Stick | Live on the booking page (checked 2026-10-27) |
| 6 | Vice golf balls: which one to play | Refresh-and-extend of the post that ranks 9 |
| 7 | Ladies golf at Stick | Only where the stock exists |
| 8 | Review Search Console, keep what worked | |

Same per-post checklist as Swing Shack: answer first, something only Stick has, two sourced figures or quotes, named author, visible Q&A, links to the service or brand page and booking, real photos, the "how this was written" line.

## Voice
Stick's real feed voice (memory `stick-voice-feed-vs-bible`): calm, product-led, "DM us", "Better begins here." Never Swing Shack's wording, never a Swing Shack mention.

## Tools now in place for Stick (this PR)
- The daily site check audits Stick's real pages and flags shared search descriptions.
- Stick has a fix queue; Fix and Improve buttons work on Stick's pages (they show copy-and-paste text until the Yoast snippet is installed on stickgolf.co.za).
- The SEO page shows Stick's fixes and change history when the brand is set to Stick. Keyword rankings stay Swing Shack only for now.

## Open
- Coach and staff input for Stick posts (same questionnaire as Swing Shack, sent to Stick's team).
- Who at Stick takes the photos.
- When the Shopify store opens (product pages change the retail plan).
