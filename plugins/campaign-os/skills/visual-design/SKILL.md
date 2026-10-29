---
name: visual-design
description: >-
  Art direction for Swing Shack, Stick and Bag Drop social graphics: one idea, one
  dominant visual move, hierarchy, spacing, type as design, controlled colour, the
  real product untouched. Load BEFORE designing, composing, prompting or reviewing
  any post, story, carousel or ad still, and before showing a design to Christelle.
  Carries the eight recipes, the three-direction rule, the hard fails and the
  40/50 publish score.
---

# Visual design — art-directed, not templated

Christelle's design rules (2026-10-27), built on her Pinterest notes of 2026-10-22 and the
flaws found in real output on 2026-10-21. **Clean is the baseline. Interesting is the job.**

Every post has:
- one clear idea
- one dominant visual move
- strong hierarchy
- deliberate spacing
- enough restraint to let the idea breathe

Related, and still in force: the measured flaws in `docs/product-post-visual-rubric.md`, the
automated checks in `campaign-os/_lib/post_qa.py`, brand colours and fonts from the brand bibles
(never inferred hex), and the copy rules in `brand-voice-truth`.

## 1. Start with the idea

Before fonts, colours or layout, answer: **what is the one visual idea of this post?**

- the product breaks through a line
- oversized type sits behind the product
- the product casts an exaggerated shadow
- a repeated shape creates movement
- a single word becomes the composition
- a thin technical grid against a large organic image
- an object floats with a deliberate, believable shadow
- text follows the angle or movement of the product

Never start with "logo top left, product centre, copy underneath". That is a template.
The design move comes first.

## 2. Movement in a still

Something should be happening. Use diagonals, repeated shapes, staggered type, shadows that
stretch one way, text on a curve, crops that imply entry or exit, repeated objects at different
scales, directional negative space, lines that run behind and in front of the subject.

The eye needs somewhere to travel, and **elements talk to each other**.
- Good: the golfer stands right; a line starts behind him and runs left into the headline.
- Bad: golfer, headline, logo — three things floating independently.

## 3. Lines

Every line does a job: connect text to product, create direction, divide information, frame a
subject, continue a product angle, build tension or rhythm. Never add a line because the layout
feels empty.

| Weight | Feels | Best for |
|---|---|---|
| Thin | technical, precise, quiet, premium | fitting, specs, TrackMan, detail |
| Thick | graphic, bold, energetic | retail, campaign headlines, promos |
| Broken / repeated | movement, speed, progression | sparingly |

## 4. Shadows

A shadow should feel designed, not applied. No cheap drop shadows.

- **Resting product:** the shadow touches it, the light direction is believable, the shadow
  matches the shape.
- **Floating product:** a clear, intentional gap — **100px or more** (`post_qa.LIFT_MIN`) —
  with the shadow meaningfully below.
- Never in between. A product hovering 20px above its shadow is a hard fail.
- Type and shapes may cast shadows too, to separate layers and make type physical.

## 5. Shapes

Tools for structure and movement: frame the product, hold copy, create contrast, guide the eye,
build rhythm. Families: circles, arcs, rectangles, long bars, frames, grids, oversized abstract
forms.

**One shape language per post.** If circles are the idea, commit to circles. Circle + triangle +
gradient blob + outline box is Canva soup.

## 6. Spacing

Spacing is design, not what is left over.

| | Feels | Best for |
|---|---|---|
| Large | premium, calm, deliberate | launches, high-end retail, fitting, brand posts |
| Tight | energetic, dense, editorial | sales, events, bold retail |

**Never make every gap equal.** Tight relationships, medium separation, large breathing room:
headline to subhead tight, headline block to product medium, product to canvas edge large. That
makes hierarchy without boxes.

## 7. Typography is a design element

Choose one mode on purpose for every post.

- **A — Big & bold.** One word dominates (NEW, GTS, HERSCHEL, BLACK FRIDAY, FITTING). Use when the
  message is simple and the product recognisable. Never crop important letters, keep it readable,
  let the product overlap where useful, no five other text blocks.
- **B — Small & detailed.** Editorial: small labels, fine rules, horizontal spec lines, tight
  alignment. Technical and considered; for fitting, equipment, TrackMan. Small on purpose, not
  because there was nowhere else to put it. (No vertical spec lines — rubric §2.)
- **C — Contrast.** Very large plus very small: GTS3, and under it TRACKMAN DRIVER FITTING ·
  NOW AVAILABLE. Big type creates emotion; small type creates credibility.

## 8. Typographic hierarchy

The viewer knows what to read first, second, last. Never give everything the same weight.
**At most 3 text levels**, plus the logo (`post_qa.TEXT_BUDGET`):

1. HERSCHEL
2. NOW AT SWING SHACK
3. DM FOR STOCK

Anything beyond that needs a very good reason. The product's name appears once.

## 9. Type follows the image

Angled club → use that angle in the layout. Golfer makes a curve → wrap text around it. Product
makes a vertical → align type against it. Subject moves left → leave space that way. The design is
built around the image, not pasted on top of it.

## 10. Colour

Fewer colours. One base, one supporting tone, one accent — and the accent does **one** job
(price, key word, CTA or product detail). Never colour every text element differently.
Tone-on-tone is the safest premium move (dark green, mid green, bright lime accent). The palette
comes from the brand bible; the restraint comes from here.

## 11. The product is sacred

Never recolour, tint, distort, rebrand, invent details, fake reflections, replace logos or alter
its shape. Cut-outs are the whole product, edge to edge. **The design happens around the product,
not to it.**

## 12. People

Never generate fake golfers when a real venue or real person exists. Never mock the golfer.

The joke can live in golf culture, obsessive equipment behaviour, weather, tee times, bags,
outfits, course rituals. Never insult ability, mock handicap, joke about bad swings or imply the
golfer is useless. **The brand is on the golfer's side.**

## 13. Realistic impossibility

Impossible concept, realistic execution: a giant ball sitting in the bay, a club floating with a
real shadow, a product breaking through a graphic wall, a bag inside an impossible architectural
frame. The object stays real; the environment becomes imaginative. The venue is the real venue.

Never: AI-looking fantasy lighting, melted objects, impossible product proportions, fake logos,
generic "AI art" backgrounds.

## 14. Negative space

Don't fill every centimetre. Before adding an element ask: does the design need more, or am I
uncomfortable with empty space? Usually it is the second.

## 15. Recipes — never the same one twice in a row

| # | Recipe | Shape of it |
|---|---|---|
| 1 | Giant Type | huge word, small product, minimal copy |
| 2 | Product Hero | large product, quiet type, lots of space |
| 3 | Editorial | small detailed type, grid, fine lines, technical |
| 4 | Shape Movement | repeated shapes, product intersects them, minimal copy |
| 5 | Shadow Play | simple ground, strong product shadow, headline interacts with it |
| 6 | Type Behind Subject | large type, real product or person overlaps it |
| 7 | Frame Break | product escapes a border or grid |
| 8 | Minimal | one product, one line, one statement |

Rotate. In a grid or a week of posts, neighbours use different recipes.

## 16. Three directions, not three colourways

For important campaigns show three genuinely different directions — e.g. A huge typography,
B minimal product photography, C graphic shape-led — not the same layout on green, black and white.
She picks a direction, not a colourway. Give a recommendation; image direction and copy line are
separate decisions.

## 17. Hard fails — reject the design if

- the product or venue is fake
- the product has been recoloured
- the product name appears more than once without reason
- more than three text groups compete
- type is unreadable
- giant type is accidentally cropped
- the shadow makes the product hover awkwardly
- a badge appears that the stock list does not support
- too many colours
- spacing feels accidental
- it looks like a fixed template
- caption and visual tell different stories
- the graphic insults the golfer
- technical information is wrong (model, price, spec — and any number needs a source)
- it looks AI-generated rather than art-directed

## 18. Creative score

Score each out of 5:

| | Question |
|---|---|
| Idea | Is there one clear visual idea? |
| Hierarchy | Do I know what to look at first? |
| Composition | Do image, type and shapes interact? |
| Typography | Is type used as design, not just copy? |
| Space | Is the layout breathing? |
| Colour | Is the palette controlled? |
| Depth | Do shadows and layering create physicality? |
| Brand | Does it feel unmistakably right for this brand? |
| Originality | Does it avoid looking like yesterday's post? |
| Accuracy | Are product, model, price and specs correct? |

**A post scoring below 40/50 does not publish.** Any hard fail overrides the score.

## Final test

1. Could this have come from any golf shop? If yes, it is not finished.
2. What is the one design decision that makes this post memorable? If there is no answer, redesign.

## How to use this in Campaign OS

1. Pick the idea and the recipe (§1, §15) before touching layout; check the last post's recipe.
2. Build it — `compose_post_for_channels()` for a known layout, real photos for product and venue.
3. Look at the render yourself. Run `campaign-os/_lib/post_qa.py`, then the human half in
   `docs/product-post-visual-rubric.md`, then §17 and §18 here, then the wiki's diagnose-a-post
   sales check. Anything real-looking (photo, generated scene, layered build) also passes the
   `reality-check` skill: real-world scale, depth, physics, light, ends in frame and load.
4. Show Christelle only what passes, with its score and the one memorable decision named in plain
   words. Prefer refusing a weak post to shipping it.
