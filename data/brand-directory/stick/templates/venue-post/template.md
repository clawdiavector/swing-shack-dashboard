# Partner plate (`stick-venue-post`)

## Intent

The photograph owns the canvas; a navy plate in the lower right carries the maker's logo, `@` and the stick wordmark. From Christelle's L.A.B. post. Brand-lifestyle look: the photo carries the post and the caption carries the words.

## When to use

- Calendar rows with **`post_type: product_lifestyle`** (always a template)
- Also picked for `subject: venue`
- A maker lifestyle photo of a product we stock (on course, in hand), or our own shop photo

## Fields

| Field | Zone | Notes |
|---|---|---|
| `vendor_name` | `partner_logo` | Maker logo from `stick/logos/vendors/<slug>.png`, tinted white, fitted into the plate. **Required** |
| `vendor_label` | `headline` | Optional text beside a small logo mark (L.A.B. style). ≤ 12 chars. Leave empty when the logo is a wordmark |
| photo | full bleed | Cover-cropped to 4:5. Keep the lower-right quarter calm: the plate covers it |

## Render / lodge

```bash
python3 campaign-os/scripts/render_post.py --brand stick --archetype stick-venue-post --channels instagram \
  --photo lifestyle.jpg --field vendor_name=RIPIT --out out/
```

Then `lodge_post.py ... --no-approve` as for the maker stack.

## Don't

- Use a generated venue or person. Real photos only.
- Name a colourway in the caption unless that exact colour is on the stock list (maker lifestyle shots often show one we don't carry).

Measured from `references/ref-01.jpg` (`lab_post.jpg`). Golden: `golden/render-instagram-ripit.jpg`, `golden/compare-refs.jpg`. Vetted 2026-10-23 (Kyle).
