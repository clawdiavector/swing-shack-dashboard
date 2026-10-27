---
name: campaign-os-carousel
description: >-
  Make an Instagram/Facebook carousel post (2 to 10 swipeable slides) for Stick, Swing
  Shack or Bag Drop: when a carousel beats a single image or a video, which kinds worked
  on the real feeds, how to plan the slides, make each one from real photos and the
  measured templates, check the set together, write the caption and get it lodged.
  Load when someone asks for a carousel, a swipe post, a multi-image post, an album,
  "several images in one post", a product-line or range post, an event or price
  breakdown in slides, or a spotlight's hero carousel.
---

# Carousel posts

A carousel is one post with 2 to 10 slides the viewer swipes through. Instagram and
Facebook take the whole set; Google Business takes one image, so it gets slide 1.

For a campaign spotlight's **hero carousel** (no-text hero, then catalogue slides), the
plan lives in `campaign-os-spotlight`; this skill is how any carousel is built, checked
and lodged.

## Before you start: can it be posted yet?

**Not as a carousel, today (27 Oct 2026).** `lodge_post.py` and approve-to-Postiz carry
one image (wiki task T18, `runbooks/posts-plan-2026-10-26/tasks/t18-carousel-posts.md`).
Postiz itself takes a list of images, so the gap is ours. Check before you promise one:

```bash
git grep -n "images_base64\|slides" origin/main -- campaign-os/scripts/lodge_post.py
```

Nothing found means T18 hasn't landed: build the full set, review it with the person,
then lodge **slide 1 only** and put "carousel, slide 1 only" in the title. Keep the other
slides in the post bank (wiki `runbooks/post-bank-2026-10-26/`) with their order. Never
post a carousel any other way (Postiz directly, Meta directly): approving is releasing,
and a person approves every post in Review.

## Is a carousel the right format?

Measured from `data/brand-directory/<brand>/feedback/instagram-audit.json` (Stick audit
5 Oct 2026, 261 posts; Swing Shack audit 13 Oct 2026, 789 posts). Median per post:

| | Stick reach | Swing Shack reach, last 12 months | Swing Shack interactions, last 12 months |
|---|---|---|---|
| Single image | 276 (104 posts) | 200 (79) | 3 |
| Carousel | 302 (27) | 225 (18) | 4 |
| Video | no data (reels bug in that audit) | 423 (103) | 10 |

So: a carousel reaches about 10% more people than a single image, and video reaches
about twice as many as either. Saves are 0 on all three, so "carousels get saved"
doesn't hold for these feeds. Use a carousel when the content **is** several things;
don't turn one idea into slides to game reach.

**Worked** (most interactions): one product line shown piece by piece (Stick "Jordan
Fade Away bags", 24; Jordan bags again, 10), the space itself (Stick "Golf is changing.
We built a space for that.", 19, reach 813; "Come browse. Ask questions. Hit a few.",
12), an event with its details (Swing Shack prize table, 23; "Only 2 four balls left",
19), a person joining the team (Swing Shack coach, 15; Stick hiring, 11).

**Didn't:** generic fitting claims spread over slides ("Generic clubs? That's cute.",
2), unsourced statistics ("87% of golfers who get fit…", 1), two near-identical launch
carousels posted the same day (3 and 2).

## Plan the slides first

Write the plan as a numbered list and get a yes before making anything:

```
Brand: Stick              Format: carousel, 5 slides, 4:5
1  hook     real photo of the Jordan bag range, no text or 3 words max
2  product  black stand bag, cut-out, name only
3  product  white cart bag, cut-out, name only
4  detail   macro of the "23" badge
5  close    what to do next: "In store now. DM us." + logo
Caption: (from brand-voice-truth)
```

- **One brand, one idea.** Every slide is the same brand (Swing Shack only Swing Shack,
  Stick only Stick; Bag Drop may name both). A Psycho Bunny carousel carries no bags.
- **Slide 1 does the work.** Most people never swipe. It must make sense alone, because
  it is also the grid tile and the Google Business image.
- **One thing per slide**, at most three pieces of text plus the logo (the `post_qa`
  text budget).
- **Same look across the set**: one template or one background, one type style. It
  should read as one post, not five.
- **Last slide is the next step**: book, DM, visit, link. Pressure goes on time, stock
  or the gear, never on the golfer or their game.
- 3 to 6 slides is plenty. 10 is the ceiling, not the goal.

## Make each slide

All slides **1080x1350** (4:5). Instagram crops every slide to slide 1's shape, so one
square slide in the set loses its top and bottom.

| Slide | How | Cost |
|---|---|---|
| Text or offer on a brand layout | `render_post.py --list` first, then one `--batch` file with a row per slide, same archetype | free, ~200ms each |
| Product cut-out | rembg recipe in `campaign-os-spotlight` ("Make the pieces"). Whole product, nothing clipped: check against the source | free |
| Several products in one slide | catalogue collage, same skill. Tall items two side by side; short items up to four | free |
| Badge or logo close-up | `campaign-os-spotlight/scripts/badge_post.py` | free |
| Hero / mood shot | a real photo first. Krea only to restyle a real photo given as the reference (`krea-lab`, OAuth connection); never a drawn product, logo or venue | ~111 credits a try |

Real venue and real product only. Check every Krea slide against the real photo
(colour, badge, trims) before it goes in the set.

## Check the set together

```bash
python3 plugins/campaign-os/skills/campaign-os-carousel/scripts/carousel_check.py \
    out/01.png out/02.png out/03.png out/04.png --out out/check/
```

It fails on fewer than 2 or more than 10 slides, or any slide not 1080x1350, and
always writes `contact-sheet.jpg` (every slide, numbered, in one row) and
`gbp-slide-1.jpg` (slide 1 at 1200x900 on a blurred copy of itself). Then look at the
contact sheet yourself, hyper-critically, before showing anyone:

- Does slide 1 stand alone? Would you stop on it?
- Do the slides look like one post (same type, same background family)?
- Any product cropped, hovering, or with letters hidden behind it?
- Any number on a slide without a source link? Then it comes off.

Show the person the contact sheet, not ten separate files.

## Caption

Load `brand-voice-truth` first. One caption for the whole set, in the feed's real shape
(Stick: short lines, calm, "DM us"). Name what's in the slides; don't narrate them
slide by slide. Run `caption_lint.py <brand> --file caption.txt`: 0 hard fails.

## Lodge

Today (before T18): slide 1 only, as above:

```bash
python3 campaign-os/scripts/lodge_post.py --brand stick --slug stick-jordan-bags-20261124 \
    --date 2026-11-24 --title "Jordan bags (carousel, slide 1 only)" --image out/01.png \
    --caption-file caption.txt --channels instagram,facebook --no-approve
```

After T18 lands: `--image` repeated once per slide, in order. Google Business gets
`gbp-slide-1.jpg` through the Google Business queue (Publish > Google Business
Profile), not the lodge. Always `--no-approve`; the person approves in Review.

## Related

`campaign-os-spotlight` (hero carousels in a campaign) · `brand-voice-truth` (caption)
· `/render-post` (template slides) · `schedule-from-anywhere` (lodging) · `krea-lab`
