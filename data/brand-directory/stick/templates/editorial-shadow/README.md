# Stick editorial shadow (`stick-editorial-shadow`)

Kyle's pick for Stick product singles (2026-10-26). A full-bleed editorial close-up of a
real product, lit so the lower third falls into deep shadow. The copy sits in that shadow,
bottom left, with no plate: mint tracked eyebrow, white product name, "AVAILABLE @", white
stick logo. Reference: `references/ref-01.jpg`.

## Render

```bash
python3 campaign-os/scripts/render_post.py --brand stick --archetype stick-editorial-shadow \
  --channels instagram,gbp --photo <krea-or-real-photo> \
  --field "eyebrow=BLACK FRIDAY · 23–30 NOV" --field "product_name=PSYCHO BUNNY POLO" --out out/
```

Fields: `eyebrow` (one line, up to 32 characters, single spaces: tracking hides double
spaces), `product_name` (up to 22 characters).

## The photo: Krea recipe (locked)

Model `google/nano-banana-pro`, `aspect_ratio` 4:5, `resolution` 2K, about 111 credits.
**One** real reference photo per product in `image_urls` (two references from different
products leak badges across, e.g. pink ears onto a plain badge). Prompt:

> Editorial product photograph of this exact {colour} {product} from the reference image.
> {The item lies flat on a warm stone-grey surface at a slight diagonal, shot from above at a
> low angle | The cap rests on a warm stone-grey surface, three-quarter front view, the badge
> facing the camera}. Hard late-afternoon window sunlight from the upper right casts crisp
> diagonal shadows. The lower third of the frame falls into deep, plain, near-black shadow with
> no detail, so text can sit there later. Crop in close on {collar / neck / badge / graphic};
> the rest runs out of frame. Keep the colour exactly {colour}, and keep the texture, trims and
> the {badge} exactly as in the reference; do not redraw, recolour, move or add any logo.
> Premium fashion-campaign mood, rich texture. No text, no words, no watermark, no hanger, no
> person, no tags.

## QA before use (wiki decision ai-image-qa-proof-and-single-retry)

Measure fabric colour in Lab against the real photo, check badge, trims and any AI-drawn
neck print. Warm light warms neutrals; light and saturated colours drift most. Fix failures
with a masked colour correction in code, not another Krea run.
