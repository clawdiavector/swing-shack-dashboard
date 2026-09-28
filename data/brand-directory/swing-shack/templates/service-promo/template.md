# ss-service-promo (Swing Shack)

Service promo poster: dimmed full-bleed venue photo, white frame, accent Montserrat Black Italic headline (2–4 lines, balanced wrap), white ExtraBold subhead, rule, centred `SERVICE @` logo lockup, green **BOOK ONLINE**, URL.

## Platforms

- Instagram feed `ig_post` 1080×1350
- Instagram story `ig_story` 1080×1920 (zone overrides)
- Facebook uses `ig_post` (4:5)

## Copy budget

- Headline (`caption_hook`): ≤52 chars, up to 4 lines
- Subhead (`cta` field): ≤44 chars, up to 2 lines
- `max_total_chars`: 96

## When to use

Tag calendar rows `post_type: service_promo` for fitting/coaching (and membership label when pillar matches). Pinned `template_id` wins over rules.

## Selection

```json
{"when": {"post_type_in": ["service_promo"]}, "use": "ss-service-promo"}
```

Untagged fitting/coaching pillars still fall back to `ss-service-frame`.
