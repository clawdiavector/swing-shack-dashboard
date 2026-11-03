# Bag Drop weekly deal (story)

**Intent:** the week's offer as a 9:16 story, drawn by the OS from typed text so the weekly
rotation (heads, shafts, putters, wedges, combos) needs no designer redraw.

**Measured from** the designer's six stories of 3 Nov 2026 (`references/ref-01..06.jpg`):
30% off Srixon & Mizuno driver and wood heads, 20% off selected shafts, 20% off putters.

## Archetypes

| id | Look | Refs |
|---|---|---|
| `bd-weekly-deal` | white top, navy panel, sage bar, white text | ref-03, ref-06 |
| `bd-weekly-deal-navy` | navy top, white panel, navy bar, sage text | ref-04, ref-05 |
| `bd-weekly-deal-makers` | as `bd-weekly-deal`, two maker logos above the offer (sage) | ref-01 |
| `bd-weekly-deal-makers-navy` | as `bd-weekly-deal-navy`, maker logos in navy | ref-02 |

`post_type` `weekly_deal` (or `deal`, `offer`) selects `bd-weekly-deal`; pin a `template_id` for the others.

## Fields

- `headline`: the offer, `20% OFF`. One line.
- `deal_detail`: up to three lines split with `|`, `PUTTERS|THIS WEEK`. Keep each line to about
  20 characters: a longer line shrinks the whole detail block.
- `vendor_name`, `vendor_name_2` (maker layouts only): file `logos/vendors/<slug>.png`. Only
  `srixon` and `mizuno` exist so far; both are needed or the render refuses.

## Known gaps

- Fonts are Saira Expanded (OFL), a stand-in fitted to the measured caps and widths. Swap in the
  designer's font files in `typography/fonts.json` when they arrive.
- Logos were cut from the stories (JPEG, ~665 px wide). Replace with the designer's PNG/SVG.
- Story only. No 4:5 feed version has been designed.
- `golden/` holds the four renders of the reference deals.
