---
name: campaign-os-carousel
description: >-
  Design and make an Instagram/Facebook carousel post (swipeable slides, 4 to 7 by
  default) for Stick, Swing Shack or Bag Drop as one sequence: a hero slide that stops
  people, slides that unfold the story, one colour story and visual thread, a simple
  close. Covers when a carousel beats a single image or a video (measured on both
  feeds), Christelle's design guide, making slides from real photos, checking the set
  together, the caption and lodging. Load when someone asks for a carousel, a swipe
  post, a multi-image post, an album, "several images in one post", a product-line or
  range post, a fitting explainer in slides, or a spotlight's hero carousel.
---

# Carousel posts

A carousel is one post the viewer swipes through. It is a sequence, not a pile of
separate posts: the first slide earns attention, the middle slides reward it, the last
slide gives the viewer somewhere to go.

**Read [`design-guide.md`](design-guide.md) in full before designing a slide.** It is
Christelle's art direction (27 Oct 2026) and it overrides anything here on how a
carousel should look. This page is the process, the checks and the plumbing.

For a campaign spotlight (one brand, hero carousel, then singles that week), the
campaign plan lives in `campaign-os-spotlight`; the carousel itself is made here.

## Before you start: can it be posted yet?

**Not as a carousel, today (27 Oct 2026).** `lodge_post.py` and approve-to-Postiz carry
one image (wiki task T18, `runbooks/posts-plan-2026-10-26/tasks/t18-carousel-posts.md`).
Postiz itself takes a list of images, so the gap is ours. Check first:

```bash
git grep -n "images_base64\|slides" origin/main -- campaign-os/scripts/lodge_post.py
```

Nothing found means T18 hasn't landed. Deliver the set (numbered slides, manifest,
caption, 4:3 hero) for review, then lodge **slide 1 only** with "carousel, slide 1
only" in the title, and keep the rest in the wiki post bank
(`runbooks/post-bank-2026-10-26/`) with the manifest. Never post a carousel another
way (Postiz or Meta directly): approving is releasing, and a person approves every post
in Review.

## Is a carousel the right format?

From `data/brand-directory/<brand>/feedback/instagram-audit.json` (Stick audit 5 Oct
2026, 261 posts; Swing Shack 13 Oct 2026, 789 posts). Wiki:
`research/carousel-performance-2026-10-27.md`. Medians per post:

| | Stick reach | Swing Shack reach, last 12 months | Swing Shack interactions, last 12 months |
|---|---|---|---|
| Single image | 276 (104 posts) | 200 (79) | 3 |
| Carousel | 302 (27) | 225 (18) | 4 |
| Video | no data (reels bug in that audit) | 423 (103) | 10 |

A carousel reaches about 10% more people than a single image; video reaches about twice
as many as either. Saves are 0 on every format. So use a carousel when the content
**is** a sequence (a range, a story, an explanation), not to stretch one idea.

**Worked:** one product line piece by piece (Stick "Jordan Fade Away bags", 24
interactions), the space itself (Stick "Golf is changing. We built a space for that.",
19, reach 813), an event with its details (Swing Shack prize table, 23), a person
joining the team (Swing Shack coach, 15). **Didn't:** generic fitting claims spread over
slides (2), unsourced statistics (1), two near-identical launch carousels the same day
(3 and 2). The audit has no slide counts, so nothing is known yet about length.

## 1. Plan the sequence, get a yes

Write the plan before making anything and show it:

```
Brand: Swing Shack        Structure: product spotlight, 5 slides, 4:5
Colour story: warm cream (dominant), dark green (support), bright green (accent),
              taken from the hero shirt
Thread: one green line that runs off each slide's right edge into the next
01_hero     shirt macro on full green, one word: NEW IN
02_intro    cream ground, green type: what it is (one line)
03_detail   close-up of the collar, tiny product note
04_range    the three colours, green shape behind
05_cta      clean cream, NOW AT SWING SHACK
Caption: (from brand-voice-truth)
```

- Pick the structure from the guide (product spotlight, fitting education, campaign
  spotlight) and give every slide one role. 4 to 7 slides; stop when the story is told.
- **One brand.** Swing Shack only Swing Shack, Stick only Stick; Bag Drop may name both.
- **Slide 1 stops people and gives little away.** It is also the grid tile and the
  Google Business image.
- Vary scale, density and space slide to slide; repeat only the palette and the thread.
- The close is a simple next step. Pressure goes on time, stock or the gear, never on
  the golfer or their game. Any number on a slide or in the caption needs a source link,
  or it comes off.

## 2. Make each slide

Every slide **1080x1350** (4:5), named `NN_<role>.png` (`01_hero.png`). Instagram crops
the whole set to slide 1's shape.

| Need | How | Cost |
|---|---|---|
| Product isolated on colour | rembg cut-out recipe in `campaign-os-spotlight` ("Make the pieces"). Whole product, nothing clipped; check against the source | free |
| Several pieces in one frame | catalogue collage, same skill. Tall items two side by side; short ones up to four | free |
| Badge or logo close-up | `campaign-os-spotlight/scripts/badge_post.py` | free |
| A brand layout with text | `render_post.py --list` first. A measured template can serve one slide, but the same archetype on every slide is the copy-paste look the guide rejects | free |
| A bolder hero scene | a real photo first. Krea only to restyle a real photo given as the reference (`krea-lab`, OAuth connection); never a drawn product, logo or venue | ~111 credits a try |

Slides are usually composed in PIL so the palette, the thread and the type scale can
change per slide. The product stays real: crop, scale, layer and shadow it, never
recolour, distort or add to it. Check every Krea slide against the real photo (colour,
badge, trims).

**Google Business** takes one 4:3 image. Recompose slide 1 at 1200x900 so the idea
survives; don't crop the 4:5. The checker's `gbp-slide-1.jpg` (slide 1 on a blurred copy
of itself) is a stopgap when there's no time to recompose.

## 3. Check the set together

```bash
python3 plugins/campaign-os/skills/campaign-os-carousel/scripts/carousel_check.py \
    out/01_hero.png out/02_intro.png out/03_detail.png out/04_range.png out/05_cta.png \
    --out out/check/
```

It fails on fewer than 2 or more than 10 slides, any slide not 1080x1350, or a file name
that doesn't start with its slide number. It always writes `contact-sheet.jpg` (every
slide numbered in one row), `gbp-slide-1.jpg` and `manifest.json` (the order).

Then look at the contact sheet yourself, hyper-critically, against the guide's three
QA lists (sections 20 to 22): reject it, redesign the hero, cut filler. Also check each
product against its source photo (whole, unaltered, letters not hidden). Fix and re-run
until you'd defend every slide. Show the person the contact sheet, not separate files.

## 4. Caption and alt text

Load `brand-voice-truth` first. One caption for the whole set, in the feed's real shape
(Stick: short lines, calm, "DM us"). Say what the carousel is about; don't narrate it
slide by slide. Run `caption_lint.py <brand> --file caption.txt`: 0 hard fails. Write one
plain line of alt text per slide (what's in it) when the post needs it.

## 5. Lodge

Before T18, slide 1 only:

```bash
python3 campaign-os/scripts/lodge_post.py --brand swing-shack --slug ss-polo-range-20261124 \
    --date 2026-11-24 --title "Polo range (carousel, slide 1 only)" --image out/01_hero.png \
    --caption-file caption.txt --channels instagram,facebook --no-approve
```

After T18: `--image` once per slide, in manifest order. Google Business gets the 4:3
hero through the Google Business queue (Publish > Google Business Profile), not the
lodge. Always `--no-approve`; the person approves in Review.

## 6. Remember what worked

Once a carousel has been live a week or two, add a row to the wiki page
`research/carousel-performance-2026-10-27.md`: brand, purpose, hero style, dominant
colour, type mode, slide count, thread, CTA, and its reach and interactions next to that
brand's median. Record the principle, not the layout: winners don't become fixed
templates.

## Related

`campaign-os-spotlight` (campaign spotlights) · `brand-voice-truth` (caption) ·
`/render-post` (templates) · `schedule-from-anywhere` (lodging) · `krea-lab`
