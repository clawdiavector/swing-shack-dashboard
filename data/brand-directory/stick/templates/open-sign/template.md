# Stick — Open sign (WE ARE OPEN)

## Intent

Venue **open-status** posts: full-bleed shop interior with a fixed navy gradient corner block carrying the white `stick` wordmark and a mint uppercase status line (`WE ARE OPEN`, `OPEN LATE TODAY`, etc.).

## Anatomy

- Full-bleed photo (`photo_full_bleed`, cover, `focus_y` 0.45) — no frame, no scrim
- Navy block: half canvas width, flush right, bottom floats 126 px above canvas bottom; horizontal gradient `navy_alt` → `navy_deep_edge`
- Wordmark: PNG asset (`assets/logo-wordmark-white.png`), centred in measured rect
- Open line: Montserrat Black, `mint`, one line, `caption_hook` uppercased, max 18 chars

## Photos (stand-ins)

**No raw text-free Stick shop photos exist yet.** Until Kyle supplies 4:5 venue shots, `photos/` holds **stand-in crops** from the reference artboards: top strip `y < 962`, centre-cropped to 767×959 (4:5). These are **not** production backgrounds — replace with real library photos when available.

Files: `stand-in-01.jpg` … `stand-in-03.jpg` (one per reference photo variant).

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | measured refs 1081×1351 |
| Facebook | `ig_post` 1080×1350 | `channel_canvas` |
| GBP | `ig_post` | same 4:5 poster |

Story override is **not** shipped in v1 (feed-only until eyeballed).

## When to use

- Tag calendar rows with `post_type: open_sign`
- Or pin `template_id` / `archetype_id: stick-open-sign` on the post

## Copy budget

- `caption_hook` → open line: **one line**, ≤ 18 chars, uppercase at render
- Default phrase in refs: `WE ARE OPEN`
- `max_total_chars`: 18
