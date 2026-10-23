# Maker stack (`stick-product-post`)

## Intent

Stick's own retail layout (the GTS2 / T250 / Vokey posts): navy-to-light gradient, maker logo, product name, `AVAILABLE @ stick`, CTA, and the real product cut-out filling the lower ~56%. Clean catalogue card; one product per post.

## When to use

- Calendar rows with **`post_type: product_post`** (rule at the top of the Stick selection list; always a template, never a one-shot)
- Any product with a clean maker pack shot: clubs, ball boxes and sleeves, rangefinders, bags

## Fields

| Field | Zone | Notes |
|---|---|---|
| `vendor_name` | `vendor_lockup` | Maker name. The logo comes from `stick/logos/vendors/<slug>.png` (slug: lower case, dots dropped, other characters to `-`, so `L.A.B. Golf` → `lab-golf`). Tinted white. **Required**: a missing logo fails the render |
| `product_name` | `headline` | 1 line, ≤ 22 chars, upper case (`101U DRIVING IRON`). Montserrat Light, centred |
| `cta` | `cta` | ≤ 23 chars. Use `DM US FOR DETAILS` (fits the approved `DM us for *.` CTA) |
| photo | `photo` | **Transparent cut-out** (PNG). Fitted without stretching (`fit: contain`, 86% wide, 94% high, top-aligned), transparency kept so the gradient shows through |

## Inputs

- Photo: an approved photo-map image or an official maker image (`_system/image-sources.json`). Never redrawn.
- Pack shots on white or light grey: cut them first with `python3 campaign-os/scripts/cutout_plain_bg.py in.jpg out.png --preview` and check the preview. Images that already have transparency (Vice, Takomo, L.A.B.) need no cut.
- New maker: save the maker's own logo (header logo on their site) as a transparent PNG in `stick/logos/vendors/<slug>.png`.

## Render / lodge

```bash
python3 campaign-os/scripts/render_post.py --brand stick --archetype stick-product-post --channels instagram \
  --photo cutout.png --field vendor_name=Takomo --field "product_name=101U DRIVING IRON" \
  --field "cta=DM US FOR DETAILS" --out out/
python3 campaign-os/scripts/lodge_post.py --brand stick --slug <slug> --date YYYY-MM-DD \
  --image out/stick__stick-product-post__instagram.png --caption-file caption.txt --no-approve
```

## Don't

- Use a dozen-box image for a product sold by the sleeve, or a colour we don't stock.
- Ship reference text (`T250 IRON SET...`) as a field.
- Approve when lodging: approval is the release.

Measured from `references/ref-01..03` (Christelle's GTS2, T250, Vokey posts). Goldens: `golden/render-instagram-{takomo,vice,callaway}.jpg`, `golden/compare-refs.jpg`. Vetted 2026-10-23 (Kyle).
