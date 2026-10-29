---
name: campaign-os-spotlight
description: >-
  Plan and make a campaign the Campaign OS way: campaign dates on the calendar, then
  one-brand weekly spotlights (a no-text hero carousel, catalogue slides, singles later
  that week), kept two weeks ahead. Covers the tools that worked on Black Friday 2026:
  Krea heroes restyled from a real photo, rembg cut-outs, catalogue collages, badge
  close-up posts, the post bank and lodging for approval. Load when someone asks to
  plan or build a campaign, a spotlight, a carousel, a hero image, catalogue or product
  posts for Stick, Swing Shack or Bag Drop, or posts "without dates" for later.
---

# Campaign OS spotlights

Agreed with Kyle on 26 Oct 2026 while building Black Friday. Full record in the wiki:
`CampaignOS/decisions/campaign-framework-two-weeks-ahead-2026-10-26.md`,
`CampaignOS/decisions/spotlight-one-brand-carousel-then-singles-2026-10-26.md`,
`CampaignOS/runbooks/black-friday-spotlight-posts-2026-10-26/index.md`,
`CampaignOS/runbooks/post-bank-2026-10-26/index.md`. Read the matching page first.

## The levels

| Level | What | Example |
|---|---|---|
| Campaign | Dates, offer, calendar steps placed on the Plan calendar | Black Friday: posts 13 Nov to 2 Dec, sale 23 to 30 Nov |
| Spotlight | One brand or product line for one week | Psycho Bunny week, Jordan bags week |
| Posts | Hero carousel first, singles later that week | see below |

**Framework:** dates on the calendar, then the first post signed off for its look (not
by pressing Approve), then it becomes a template, then week 1, then a keeper fills each
week so there are always two weeks ahead, gated by approval. A person approves every
week.

## Rules

- **One brand per spotlight.** If the hero shows a brand, every slide and every single
  that week shows the same brand. Captions name only that brand and the shop.
- **Approving is releasing.** Lodge with `--no-approve`. Never approve unasked.
- **Teasers don't state a discount.** Offer wording only from the sale's first day.
- **Real products only.** An image that sells a product shows that exact product:
  Krea may restyle or fix a real photo given as a reference, never invent a new
  product or logo. Check every such result against the real photo (colour, badge,
  trims); expect drift and redo when it's wrong. Standalone art that sells no product
  may be generated freely. Never an invented bay or shop shown as ours.
- **Real-looking means real scale.** Heroes and singles pass the `reality-check` skill
  (sizes, depth, physics, light, ends in frame, load) before anyone sees them.
- **Channels:** Instagram + Facebook through the lodge; Google Business takes one 4:3
  image through the Google Business queue (Publish > Google Business Profile).
- **Black Friday captions with "% off"** fail Stick's caption lint. Herman's wording
  needs a standing exception or a reword; ask Kyle.

## Every format, every platform (Christelle, 28 Oct 2026)

A campaign uses every format. Each moment (teaser, reveal, offers live, sale days, last
day, thank-you) gets one idea, made as a **content pack**: one piece per format, not one
image resized. Wiki: `CampaignOS/decisions/campaign-formats-and-platforms-2026-10-28.md`.

| Moment | Still | Carousel | Reel / video | Stories | Google Business |
|---|---|---|---|---|---|
| Teaser | yes | | yes | countdown story | optional, no offer |
| Reveal | | offer, then products | yes | yes | Offer post |
| Each sale day | feed post rotates still, carousel, reel | | | 2-3 a day | |
| Last day | | | yes | yes | yes |
| Thank-you | yes or carousel | | | yes | |

| Platform | Size | What changes |
|---|---|---|
| Instagram feed, carousel | 4:5, 1080x1350 | The designed version; keep the idea in the middle 3:4 (profile grid crop) |
| Reels, TikTok, Shorts | 9:16, 1080x1920 | Movement in the first second, text on screen, licensed music; text out of the top ~250px and bottom ~350px |
| IG and FB Stories | 9:16, 1080x1920 | A new layout, headline in the middle band, one action; stickers are added by hand (Postiz can't) |
| Facebook feed | 4:5, same file | A link works in the caption |
| Google Business | 4:3, 1200x900 | Offer post with start and end dates; plain text, no hashtags |

Reels: real video when we have it; otherwise `scripts/retail_reel.py` animates real
product photos (organic only; ads are real human video only). The product rests on its
contact shadow, never hovers. Stories go to Postiz with `scripts/send_story.py`.

## Make the pieces

| Piece | How | Cost |
|---|---|---|
| Hero (slide 1, no text) | Krea MCP connector, `google/nano-banana-pro`, the real photo uploaded via `get_upload_url` and passed as `image_urls`, `aspect_ratio: "4:5"`, `resolution: "2K"`. Prompt: "extreme macro close-up of this exact …, keep the logo shape exactly, no text". Run `preflight: true` first | ~111 credits a try |
| Cut-outs | `rembg` with `birefnet-general-lite` (separate venv: `pip install "rembg[cpu]"`). Threshold the alpha (<60 → 0) before compositing; pad any drop-shadow canvas or it shows as a box | free |
| Catalogue slide | Cut-outs of one line on the brand's navy fade, offer or line name on top, logo at the bottom. Two tall items (bags) side by side; four only if short (polos, tees, caps) | free |
| Single | `render_post.py` maker stack (`stick-product-post`, needs `logos/vendors/<maker>.png`) or partner plate (`stick-venue-post`) | free |
| Badge close-up post | `scripts/badge_post.py`: straightens and centres the badge, white text with black outline, 4:5 plus a 4:3 on a blurred fill | free |
| Caption | `caption_lint.py <brand> --file caption.txt`: 0 hard fails | free |
| Lodge | `lodge_post.py --brand … --slug … --date … --image … --caption-file … --channels instagram,facebook --no-approve` | free |

Whole shirts on hangers photograph badly. Show detail instead: badge macros, fabric,
a flat-lay (Krea editorial from the real shirt, checked), or the approved packshots.

## Posts with no date

Campaign OS can't hold an undated post yet: `lodge_post.py` needs `--date`. Until the
"undated posts on the Shelf" change lands (wiki task T19), finished posts wait in the
wiki post bank with their lodge command. Mark a banked post "Used on" when it's lodged.

## Carousels

`lodge_post.py` and approve-to-Postiz carry one image today (wiki task T18). Lodge the
hero as slide 1 only and say so in the title. Planning, checking and lodging any
carousel: `campaign-os-carousel`.

## Known traps

- `gbp` isn't an allowed lodge channel for Stick: the server refuses it.
- A lodged post makes its own calendar entry; it doesn't fill a placed plan step, so
  that day shows twice. Remove the plan step after approving.
- The template renderer needs `images/tagline-light.png` and other git-ignored brand
  assets; copy them from the main checkout when rendering in a fresh worktree.
- Maker sites (Psycho Bunny) block automated logo downloads; a person saves the logo.
