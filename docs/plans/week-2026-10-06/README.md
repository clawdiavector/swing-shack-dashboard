# Week of 6–10 October 2026

Rendered deterministically from measured templates. No image model, no credits.

```bash
python3 campaign-os/scripts/render_post.py --batch docs/plans/week-2026-10-06/week.json --out out/week-2026-10-06/
```

## What is in the week

| Day | Brand | Template | Copy |
|---|---|---|---|
| Mon | Swing Shack | `ss-fitting-headline` | HIT MORE GREENS WITH AN / IRON FITTING |
| Tue | Swing Shack | `ss-did-you-know` | SMASH FACTOR NOT SWING SPEED |
| Wed | Swing Shack | `ss-service-promo` | YOUR DRIVER ISN'T MATCHED TO YOUR SWING |
| Thu | Swing Shack | `ss-zen-venue-promo` | ZEN SWING STAGE / FOUR TRACKMAN BAYS NEXT DOOR |
| Fri | Swing Shack | `ss-lesson-corner` | 1-ON-1 TRACKMAN COACHING |
| Mon | Stick | `stick-shop-corner` | NEW IN (Psycho Bunny Maverick) |
| Tue | Stick | `stick-service-start` | FULL SHAFT MATRIX / FIT FIRST. BUY SECOND. |
| Wed | Stick | `stick-shop-corner` | PSYCHO BUNNY (hip detail) |
| Fri | Stick | `stick-service-start` | PRECISION WORKSHOP / FIT FIRST. BUY SECOND. |

Every line is an approved headline from `copy/headlines.md`, an approved CTA from
`copy/ctas.md`, or a claim in `knowledge.json` → `verified_facts`. No price, offer
or statistic is invented, per each brand's `rules.no_fabrication`. Stick copy
makes no mention of Swing Shack, per its `ctas.md`.

## Check before posting

- **`ss-lesson-corner` names a coach.** "CATHERINE LAU PGA PROFESSIONAL" is baked
  into the template as static copy. Confirm it is current.
- **Stick's two service cards use a pale stand-in photo.** `templates/service-start/photos/`
  holds washed-out plates, so the card reads as navy type on near-white. Real venue
  photography would carry it. The 24 walkthrough photos now in
  `images/Location/In Store Photos for walkthrough/` are exactly that, and are HEIC,
  which PIL cannot open here — convert them to JPEG and these cards improve at once.

## Thursday has no Stick post

Not an oversight. Two candidates were cut after looking at the renders:

- **`stick-location-drive`** double-prints its locked headline. The map-photo style
  has no clean plate, so the renderer crops the map out of `references/ref-01.jpg` —
  a finished post whose own headline sits inside the crop region. Its
  `photos/README.md` calls this a stand-in. It needs a real location photo.
- **A Vessel arrivals post.** There is no clean Vessel photograph to use.

That second point is the larger finding: **Stick's Drive `Products/` folder is a
library of finished posts, not raw product photography.** Nearly every file already
carries the navy `@ stick` plate, so compositing on top double-prints the lockup.
The `psychobunny-maverick/` shots used here are hand-added and are the exception.
Shop-corner posts need clean product photography that mostly does not exist yet.
