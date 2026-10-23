# Swing Shack - Product post: type hero (dark)

## Intent
Dark poster. A huge two-line headline, the products fanned along the bottom like a lineup. For a range or family.

## How to use
- Layout name: `type-hero` (1 to 3 product(s)). Render with
  `python campaign-os/scripts/render_product_post.py post.json out.jpg` or `render()` in
  `campaign-os/_lib/product_post_templates.py`.
- Copy: brand, two headline lines (each 14 characters or fewer), one label per product, optional tag, sub and cta.
- Image: the real packshot on white. It is cut out by flood fill, never redrawn.
- Accent: one of green, orange, blue, purple. One per post.

## Repeating (rotation)
Three layouts live in `product-type-hero`, `product-one-hero` and `product-pick-yours`. Never reuse a layout within
two product posts, so each one returns at most every third post. `next_layout(history)` picks the one used longest ago.
Never run two Swing Shack product posts for the same product in one week.

## Best for
a range or family of 2 to 3 models from one maker (Z-Star XV / Z-Star / Diamond, Chrome Tour / X / Triple Diamond)

## Don't
- Redraw, retouch or invent a product. Real packshots only.
- Print a performance or ranking claim ("longest", "straightest", "tour proven"); any number needs a source link.
- Say "just landed" unless the stock list status is new, or "back in stock" unless status is back.
- Use the Stick look here: Swing Shack only, never Stick.

## Goldens
`golden/case-01.jpg`, `case-02.jpg` are rebuilt from `cases.json` with
`python campaign-os/scripts/render_product_post.py --goldens --images <folder with the maker images>`.
Source images are git-ignored (brand images are not in git); see the wiki runbook for where they come from.

Wiki: CampaignOS/runbooks/swing-shack-product-post-templates-2026-10-23.md
