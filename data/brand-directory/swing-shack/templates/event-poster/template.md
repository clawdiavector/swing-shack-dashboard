# ss-event-poster — event schedule poster (layout A)

Measured from Content Bank `rc_static` / `rc_story` (Ryder Cup family). Layout B hero refs (`RC1`, `rc3`) are in `references/` for comparison only — out of scope for this archetype.

## When to use

Tournament or event **schedule** posts: two-word title, date range, stacked rows (players, days, formats, entry fee). Story adds an optional CTA row.

Tag `post_type: event_poster` (or `event`, `tournament`, `comp`) or pin `template_id` / `archetype_id` on the calendar record.

## Platforms

| Canvas | Size | Source ref |
|--------|------|------------|
| `ig_post` | 1080×1350 | `ref-01.jpg` (`block_anchor: center`) |
| `ig_story` | 1080×1920 | `ref-02.jpg` (full `canvas_overrides.ig_story`) |
| Facebook | 4:5 via `channel_canvas` | same as post |

GBP is omitted — stacked rows do not read in landscape.

## Copy budget

- **Hook:** exactly **two words** (`RYDER CUP`, `CLUB CHAMPS`). Word 1 → red title zone; word 2 → blue.
- **Date line:** `offer_subject` (e.g. `27 & 28 SEPTEMBER`).
- **Rows:** `bio_1`, `bio_2`, `bio_3`, `benefits` (pipe explicit wrap for two-line red blocks), `caption_body`, `price`. Tune `emphasis_words` per event when label/value split changes.
- Story-only optional row: `cta` (e.g. `DM US TO ENTER`).

## Photos

`photos/` currently uses **stand-ins** cropped from `rc_story` until Kyle supplies the raw US/EU flag backdrop.
