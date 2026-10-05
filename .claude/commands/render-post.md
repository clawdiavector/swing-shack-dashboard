---
description: Render a post from a measured template — deterministic, free, correct text
allowed-tools: Bash(python3 campaign-os/scripts/render_post.py:*), Bash(ls:*), Bash(find:*), Read, Write, Grep
argument-hint: "[brand] [archetype] | --list | week"
---

## Use this before reaching for an image model

If a layout is known, render it. `compose_post_for_channels()` produces
pixel-identical output in ~200ms with correct text, for free. An image model
garbles type, drifts off palette, invents logos, and costs credits and a one-shot
slot per attempt.

On 2026-10-05 a full day went into art-directing a poster this already rendered
from an existing template, and the "winning prompt" turned out to be a
description of a reference image sitting in the template pack. **Check
`--list` first, every time.**

## Start here

```bash
python3 campaign-os/scripts/render_post.py --list
```

Then read what the template wants before filling it in:

```bash
python3 campaign-os/scripts/render_post.py --brand swing-shack --archetype ss-service-promo --describe
```

`--describe` prints each field's name, its line and character budget, and
whether the template appends its own suffix.

## Render one

```bash
python3 campaign-os/scripts/render_post.py --brand swing-shack \
  --archetype ss-fitting-headline --channels instagram \
  --field caption_hook="HIT MORE GREENS WITH AN" \
  --field service_lockup="IRON FITTING" --out out/
```

## Render a week

Write a JSON list and render it in one pass — this is the shape to use when the
ask is "make the week's posts":

```json
[{"brand": "stick", "archetype": "stick-shop-corner", "slug": "mon-arrivals",
  "channels": ["instagram"], "photo": "data/brand-directory/stick/images/Products/x.jpg",
  "fields": {"caption_hook": "NEW IN"}}]
```

```bash
python3 campaign-os/scripts/render_post.py --batch week.json --out out/week/
```

Each post renders independently; one failure does not stop the rest, and the exit
status is the number that failed.

## Rules that save a wasted hour

- **`fields` is keyed by each zone's `source`, not by the zone name.** `--describe`
  prints the right keys.
- **A zone may append its own `text_suffix`.** `ss-service-promo`'s
  `service_lockup` adds `" @"`, so pass `"BALL FITTING"`, never `"BALL FITTING @"`.
  `--describe` flags this.
- **Respect the budget, and distrust it slightly.** 7 of 14 packs cannot render
  copy filled to their own declared `max_lines × max_chars_per_line`
  (`/verify-specs`, `archetypes.declared_budget`). Stay comfortably under it.
- **Photos.** Archetypes marked `photo required` take one from their own pack by
  default; pass `photo` to choose. Raw brand imagery lives under
  `data/brand-directory/<brand>/images/` — pull it with
  `scripts/ingest_public_drive_folder.py --brand <brand>`, it is not in git.
- **Not every archetype renders.** Those without a `template_pack` are specs only;
  `--list` marks them. Measure a new one with the `campaign-os-template` skill
  rather than prompting a model for the layout.

## After rendering

Show the user the files. If a layout genuinely does not exist yet — Stick's
`@ stick` partner panel and the flat-navy offer card both recur on the feed and
have no template — say so instead of generating a one-off: measuring it once with
`campaign-os-template` makes it free forever.
