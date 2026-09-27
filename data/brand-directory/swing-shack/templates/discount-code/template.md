# ss-discount-code — fitting discount / promo code lockup

Measured from Content Bank `fitting_discount_post.jpg` (1081×1301) and
`fitting_discount_story.jpg` (1081×1921). One design at two canvases: near-black
vertical gradient, opaque white frame, centred logo, three left-origin hero lines
(percent, subject, expiry), horizontal rule, member disclaimer, upright Inter CTA
block (`USE CODE` / code / `ONLINE TO CLAIM`).

## When to use

Calendar records tagged `post_type: discount_code` (also `promo_code`, `offer`).
Pin `template_id: ss-discount-code` to override selection.

## Copy budget

| Zone | Source | Notes |
|------|--------|-------|
| Headline | `compose_headline` / caption hook | e.g. `15% OFF` |
| Subhead | `compose_subject` | e.g. `ALL FITTINGS` |
| Tagline | `compose_expiry` (optional) | e.g. `UNTIL END OF MAY` |
| CTA | `compose_cta` | promo code string |
| Statics | archetype literals | disclaimer + CTA kicker/tail |

## Platforms

- Instagram feed (`ig_post` 1080×1350)
- Instagram story (`ig_story` 1080×1920) — full `canvas_overrides`, not block_anchor alone
- Facebook → same 4:5 as feed (`channel_canvas`)

No GBP — stacked nine-line layout does not read in 4:3.

## Assets

- `assets/logo-white.png` — lockup extracted from story ref (full SHACK tee)
- `references/ref-01.jpg`, `ref-02.jpg` — Content Bank sources
- `golden/compare-*.jpg` — reference vs render sheets
