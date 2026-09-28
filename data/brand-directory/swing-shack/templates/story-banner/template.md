# ss-story-banner (Swing Shack)

Generic **photo + headline + logo** fallback banner. Bootstrap scaffold geometry (same zone table as `ss-photo-post`), **not** measured from a Content Bank reference set — see plan handoff §0.

## References

`references/` is intentionally empty: no unclaimed Content Bank group maps to this generic layout. Compare QA uses composed goldens only (`golden/compare-sheet.jpg`), not `compare_sheet.py` ref diffs.

## Platforms

- Instagram feed `ig_post` 1080×1350 (base canvas)
- Instagram story `ig_story` 1080×1920 — logo re-anchored via `canvas_overrides.ig_story` (avoids `block_anchor: center` clipping the logo off-canvas)
- Facebook → `fb_post` 1200×630, GBP → `gbp_post` 1200×900 (pre-existing channel mapping; spot-check goldens)

## Copy budget

- Headline (`caption_hook`): ≤80 chars total, up to 2 lines × 24 chars
- Hero photo: required at compose time (`photo_bytes`); standin under `photos/` is for goldens/tests only

## When to use

Tag `post_type: story_banner` or pin `template_id` / `archetype_id` to `ss-story-banner`. Plain scaffold — not a measured promo lockup. For styled promos use `ss-service-promo`, `ss-discount-code`, etc.

## Selection

```json
{"when": {"post_type_in": ["story_banner"]}, "use": "ss-story-banner"}
```

Pinned `template_id` wins over rules.
