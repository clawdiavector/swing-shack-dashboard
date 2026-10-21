# Product post visual rubric

The pass a person (or a vision model) makes on every product post before it goes to Christelle.
`campaign-os/_lib/post_qa.py` automates the measurable half. Everything below was found by looking at
real output on 2026-10-21 (Stick, Callaway Chrome Soft and Psycho Bunny polo). Score each item pass or fail.
Any fail sends the post back.

## 1. Is the product IN the set, or pasted on it?

| Check | Fail looks like | Why it happens | Fix |
|---|---|---|---|
| Grounded or clearly levitating | The product hovers a little above the surface | A small lift with a weak shadow | Rest it (shadow touching) or levitate clearly (gap of 100px or more, soft shadow below). Never in between |
| Contact | No dark line where it touches | Only a soft blob shadow | A tight occlusion shadow under the footprint plus a cast shadow along the surface |
| Perspective | A straight-on product on a surface seen from above | The product photo is straight-on, the set is not | Use a straight-on (eye-level) set for products that rest. Levitating products can use any set |
| Light direction | Shadow falls the wrong way or with no relation to the light in the set | One shadow rule for every set | Shadow direction comes from the set's light direction |
| Sharpness | The product is razor sharp against a soft set | Product is a studio photo, set is upscaled | Soften the product very slightly (about half a pixel) and defringe the edge |
| Edge | A pale halo around the product | Old background in the cut-out | Defringe: pull the edge in one pixel |
| Colour | The product has changed colour | Tinting toward the set | Never tint. Shadows and occlusion only |

## 2. Is there too much text?

| Check | Fail looks like | Fix |
|---|---|---|
| Name repeated | "Psycho Bunny" in the giant word, headline, caption and spec line | The product's name appears once in text at most |
| Text budget | More than three pieces of text (giant word, headline, caption) plus the logo | Cut. The product and the set carry the post |
| Competing treatments | Outline word, italic headline, crop marks, spec line, badge together | One flourish at most. No vertical spec line |
| Headline says nothing | A line that repeats the brand, or does not suit the product | Ideas that name a brand stay with that brand; do not write the brand again |
| Caption repeats | Caption restates the name already in the giant word | Caption says only where it is: "In store, Paarl." |

## 3. Are the layers clean?

| Check | Fail looks like | Fix |
|---|---|---|
| Giant word cropped | The first letter is cut by the canvas edge | The word fits inside the canvas with a margin |
| Giant word hidden | The product covers most of it | At least 78% visible, else shrink or move the product |
| Weak outline | A thin outline on a mid background | Thick stroke, full opacity, or use solid or tone |
| Collisions | A badge or headline on top of another element or the product | Zero overlap between badge, headline, word and product |
| Zone | Headline on a busy area | Calmest zone, with a soft scrim |
| Logo | Logo unreadable on its ground | Navy or white by the pixels behind it; top-left unless blocked |

## 4. Does it feel right?

Not measurable. Ask: would this stop a thumb? Is there one clear focus? Does it look like a photograph
of a real product in a real set, with one idea of design on top? Does it look like something a
five-year-old made in Paint (flat, floating, clip-art)? If yes, it fails whatever the numbers say.

## Order of fixes
1. Grounding and perspective (most visible).
2. Text budget.
3. Layer collisions.
4. Detail (edge, sharpness).
