# ss-service-frame (Swing Shack)

Generic fitting/coaching service tile: solid brand field, headline, optional lower photo, logo. **Synthetic / not reference-measured** — stub geometry wired before wave-2 pack work.

## References

No dedicated Content Bank art for this family. The only filename candidate (`frame1.jpg`) is a partial export of the creative already packed as `ss-discount-code`. Do not confuse with peer **`stick-service-frame`** (navy field + full-bleed teal CTA band + wordmark/tagline footer).

## Platforms

- Instagram feed `ig_post` 1080×1350
- Other channels use the archetype default canvas mapping in `visual-spec/archetypes.json`

## Copy budget

- Headline (`caption_hook`): ≤80 chars, up to 2 lines
- Optional hero photo in lower zone when `photo_bytes` supplied

## When to use

Default for fitting/coaching pillars when `has_product_item: false` and no more specific `post_type` rule matches. Tag `post_type: service_promo`, `service_frame`, etc. to pick measured promos instead. Pinned `template_id` wins over rules.

## Selection

```json
{"when": {"pillar_in": ["fitting", "coaching", "ss-fitting", "ss-coaching"], "has_product_item": false}, "use": "ss-service-frame"}
```

## Goldens

`golden/render-instagram-no-photo.png` and `golden/render-instagram-with-photo.png` — compose QA only, not compared to reference JPGs.
