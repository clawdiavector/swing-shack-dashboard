---
name: reality-check
description: >-
  Standing rule for every real-looking image (a photo, a generated scene, or a layered build
  with real products and generated people) for Stick, Swing Shack or Bag Drop: before anyone
  sees it, check real-world scale with reality_check.py, then depth, physics, light, shape,
  stock, people, ends in frame and load. Load BEFORE showing, sending or lodging any
  photorealistic post, carousel slide, story, ad still or mockup, and whenever someone says an
  image "looks off", "looks fake", "looks wack" or asks whether the sizes are right.
---

# Reality check

Christelle's rule (29 Oct 2026): every real-looking piece passes a reality check before she
sees it. A generated scene can be sharp, on-brand and colour-correct and still look wrong,
because people judge size, weight and light without thinking about it.

How the rule came about: on the first "Fresh off the pin" plates the caps measured 2.4x their
real size against a 2.13 m flagstick. The next round passed on numbers but showed a man leaning
his weight on a 13 mm pin that ran off the top of the frame. Both looked "wack" at a glance.

Applies to anything photoreal: generated scenes, layered builds, enhanced photos, mockups.
Flat graphics and pure type posts are exempt; "realistic impossibility" (visual-design
section 13) is not: the impossible idea is fine, but everything in it still obeys these rules.

## The nine checks

1. **Sizes.** Measure the objects in pixels, mark one you trust as the reference (a person,
   the flagstick, the hole, a ball) and run:

   ```bash
   python3 plugins/campaign-os/skills/campaign-os-carousel/scripts/reality_check.py plate.json
   ```

   `plate.json` is a list like `[{"object": "person", "px": 1620, "ref": true},
   {"object": "cap", "px": 186}]`. Real sizes and their sources live in
   `campaign-os-carousel/real-sizes.json` (ball 42.67 mm, hole 108 mm, flagstick 2.13 m, cap
   about 19.5 cm across, person about 1.72 m). Any FAIL is fixed before anyone sees it. An object
   that isn't in the table gets added with a source, never guessed.
2. **Depth.** Only compare objects at the same distance. Further away is smaller, higher in the
   frame and softer; a "far" object that is sharp and large is wrong.
3. **Physics.** Everything hangs from, rests on or is held by something: a contact point, a
   shadow where it touches, gravity in the fabric. Nothing floats unless floating is the idea.
4. **Light.** One sun, one direction: highlights and cast shadows on the product agree with the
   scene. A product lit by a studio softbox inside a golden-hour scene looks pasted.
5. **Shape.** The product's proportions match its official photo (crown height to brim, bag
   height to width). Badges and logos are checked up close against the packshot; colour against
   the official listing.
6. **It exists.** The product, in that colour, is on the brand's current stock list. A colour in
   an old shoot or a maker's catalogue is not proof it's on the shelf.
7. **People.** Hands, fingers, teeth and eyes at 100%; feet on the ground with a shadow; no
   invented logos on their clothes.
8. **Ends in frame.** A long object the eye uses for scale (a flagstick, a club, a pole) shows
   its end, or it reads as endless. A flagstick running off the top of the frame looked far
   taller than the man beside it even at a true 2.13 m. Numbers passing is not the same as
   looking right.
9. **Load.** Can the thing carry what the picture puts on it? A flagstick is a 13 mm rod loose
   in a cup: golfers hold, pull or attend the pin; they never lean on it. Picture it happening
   on a real course.

Then look at it as a stranger would, at phone size. If anything feels off, it is off, whatever
the numbers say.

## Where it sits in the work

| Work | When to run it |
|---|---|
| Krea generation (`krea-lab`) | On every render, before any layering or copy |
| Layered builds (scene + people + product) | After layering, before copy |
| Posts and mockups (`visual-design`) | With the visual rubric, before the sales check |
| Carousels (`campaign-os-carousel`) | On every slide, before the contact sheet goes out |
| Campaign spotlights (`campaign-os-spotlight`) | On heroes and singles |

When showing the work, say it passed and give the key numbers (for example: man 1.72 m,
flagstick 2.23 m, cap 19.7 cm). If something can't be checked (stock not readable), say so.
