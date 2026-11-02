---
name: campaign-os-efforts
description: >-
  Make the monthly marketing efforts pack for Stick and Swing Shack: five things people
  take part in (a weekly leaderboard, a challenge night, an advent countdown, a hunt, a
  weather-triggered push), each with art-directed mockups on real photos, a dated roll-out,
  where it's shared, what to confirm and how we'll know it worked, on one review page. Load
  when someone asks for marketing efforts, activations, campaign ideas like the leaderboard,
  competitions, challenges, giveaways, engagement ideas, "5 ideas a month", or next month's
  efforts pack.
---

# Monthly efforts pack

An effort is something people **take part in** over days or weeks, not a one-off post: a
leaderboard they climb, a night they come to, a door they open each morning, a shelf they
count. Christelle asked for five a month, each with mockups and a roll-out plan
(2026-10-29). The December 2026 pack is the worked example (end of this page).

## When

A pack per month, **ready by the 15th of the month before**. Nothing goes on the calendar
until Christelle has picked and Herman has approved any prize or discount.

## Steps

1. **Read what exists.** Last month's pack, the wiki idea bank
   (`research/idea-bank-from-creative-references-2026-10-29.md`) and the reference pages
   (`research/creative-reference-profiles-2026-10-29.md`,
   `research/design-led-accounts-for-offer-posts-2026-10-29.md`).
2. **Check the real facts before inventing anything.** Competitions and events the venue
   already runs are on its own posters: `data/brand-directory/<brand>/images/Others/` and
   `Services/` (December found a Dec–Feb wedge comp this way). Prices are in the booking
   widgets; hours in the venue facts; products in the stock list.
3. **Pick five.** Both brands, one brand per effort. Vary the mechanic: a ladder or
   leaderboard, a challenge or event night, a countdown or advent, a hunt or game, a
   reactive trigger (weather, a sports moment), a people series. No two alike.
4. **Write each one:** how it works (3 bullets), a dated roll-out table, where it's shared
   (feed, stories, reels, Google Business, WhatsApp status, the venue's own screens and
   posters), **what to confirm first**, and how we'll know it worked.
5. **Choose a treatment per effort, from a reference** (recipes below). Decide the
   treatment before opening a photo.
6. **Make the mockups** with `scripts/mockup_kit.py`: a story (9:16) and a feed post (4:5)
   per effort. Review every one at full size, hyper-critically, and fix before showing.
7. **One review page** (Artifact): December at a glance, then per effort the board, how it
   works, roll-out, shared on, confirm first, measure. Private until she shares it.
8. **File it**: add the pack to the wiki idea bank page.
9. **After her yes**: place the efforts on the Plan calendar (ask first; it's live), and
   send the confirm list to Herman.

## Rules (all of them, every effort)

- Brands are separate: Swing Shack only Swing Shack (Randburg, indoor), Stick only Stick (Paarl).
- Real product and real venue; nothing faked as ours. Swing Shack is always indoors, always
  "Swing Shack", the logo from `main` (fixed in PR #259).
- Lines written for a stranger scrolling (`feedback-viewer-first-copy`), confident never
  needy, never at the golfer's expense, numbers only with a source.
- No prize or discount without Herman's yes. No names or faces without the person's OK.
- Image rights before using anyone else's picture. No celebrity or athlete imagery.
- Sample names, scores and stand-in people are marked **MOCKUP** on the board.

## Art direction: never a raw photo with text on it

Christelle caught this on 29 Oct 2026: a morning of studying creative brands, then mockups
made of unedited phone photos with type laid over. Every real photo is **graded**
(`grade()`: highlights recovered, contrast, warmth, sharpen) and then cut out, framed or
placed into a designed world. The five December recipes:

| Recipe | How | Traps met |
|---|---|---|
| **Arcade high-score screen** (leaderboards) | `pixel_text()` sized by measuring every line to the screen, `glow()`, `scanlines()`, `vignette()`; a pixel scene (golf hole, ball flight) fills the bottom. The feed post puts the same screen on the venue's real TV with `perspective_paste()` | Guessing the pixel size: text ran off and ranks collided. Find the TV's corners by drawing a grid on the photo, not by eye |
| **Drawn storm** (weather triggers) | Gradient night sky, blurred cloud blobs, a jagged bolt with a flash lighting the clouds (`glow()`), a skyline with a landmark, thin rain; the real venue graded warm in a lit window | A thin bolt reads weak; keep it clear of the type; heavy rain dulls the words |
| **Fight-night poster** (challenge nights) | rembg cut-outs, `padded()` then `rim()` in the accent colour, the challenger as a dark silhouette with "?", spotlights, halftone, `grain()`; the title sized to fit the width | Rim light drawn without padding showed as boxes; cut-outs pick up people standing behind (erase, check on magenta); a real person stands in until photographed |
| **Papercraft doors** (advent, countdowns) | Raised tiles (bevel + drop shadow); an open door = a lit recess with an inner shadow, the real product on its contact shadow, the door panel hinged out with its own shadow | Doors swung over their neighbours: the grid gap must be wider than the panel; black products shot against the wall need the true-black grade (`campaign-os-carousel`) |
| **Sticker and loupe** (hunts, games) | The real photo graded and die-cut as a tilted white-bordered sticker on a halftone; the answer through a loupe joined by a line to the real target | The claim must match the photo ("one bunny" was false: the shelf had several, so the question became "how many?"); find the target by zooming in, never place a circle on a guess |

The build scripts for all five, with the boards: wiki `research/efforts-december-2026/`
(`v2_1_ladder.py` to `v2_5_bunnies.py`). Copy the pattern, not the paths or coordinates.

## Known traps

- Some venue photos are iPhone HEIC files named `.jpeg`: `pillow_heif.register_heif_opener()`.
- rembg (`~/rembg-venv`) runs one image per process; a batch can run out of memory.
- Instagram feed images don't load in the built-in browser pane; look at reference feeds in
  Christelle's Chrome (`instagram-reference-browsing-limits`).

## Worked example: December 2026

Wedge Ladder, Storm Check and Beat the Coach (Swing Shack); 12 Days of Stick and How Many
Bunnies? (Stick). Review page: https://claude.ai/artifact/QaSzeAGBduzQLZAsZccLuR (private,
Christelle's). Record and confirm list: wiki `research/idea-bank-from-creative-references-2026-10-29.md`.

## Related

`campaign-os-carousel` (carousels inside an effort) · `visual-design` (her design rules) ·
`brand-voice-truth` (captions) · `campaign-os-wiki` (filing the pack)
