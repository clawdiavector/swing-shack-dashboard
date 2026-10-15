# Campaign OS — Story reposts (Foreman)

Someone sends a link to a good Instagram or Facebook post and wants it shared to
the brand's Stories. Foreman adds it to the Stories list on the Today page. A
person taps the link and uses the app's own **Share to story** button. Foreman
never downloads or publishes anything.

## When

A Telegram message contains an `instagram.com`, `instagr.am`, `facebook.com`,
`fb.watch` or `fb.me` link and the sender wants it on a story ("story this",
"repost", or just the link on its own in the stories chat).

## Ask first

| If missing | Ask |
|---|---|
| **Brand** | "Which brand — Swing Shack, Stick, or Bag Drop?" Do not guess. |
| What it is | Nothing. A note is optional: take a few words if the sender wrote them. |

Brand ids: `swing-shack`, `stick`, `bag-drop`.

## Do (bearer `$COS_JOB_TOKEN`, never print it)

`POST https://swing-shack-dashboard-production.up.railway.app/api/stories`

```json
{"brand": "swing-shack", "url": "<the link as sent>", "note": "<few words, optional>", "added_by": "<sender's first name>"}
```

- `201` → reply "Added to today's stories for <brand>."
- `200` with `"created": false` → reply "Already on the list."
- `400` → say why (`error`), e.g. not an Instagram or Facebook link.

Mark one done: `POST /api/stories/<id>/done`. Undo: `/open`. List: `GET /api/stories`.

## Never

- Download the media or post it through Meta. Reposting with the app's own button keeps the original credit.
- Add links from sites other than Instagram and Facebook.
- Suggest a brand's latest releases. Pick things the shop stocks or services it offers.

## Today's idea

`GET /api/stories/suggestion?brand=<id>` returns what to feature today and which
stocked brand to repost from (Instagram and Facebook page links). If someone asks
"what should we story today", read it out: feature, brand, and the `look_for` line.
The brand lists are `data/brand-directory/<brand>/story-brands.json`. RipIt has no
handles yet and is skipped until they are added.

## Finding specific posts

`GET /api/stories/candidates?brand=<id>` returns the best recent posts to repost, read
from the pages in `story-brands.json` (retail brands and golf "moments") with Meta's
read-only business_discovery. Launches, sales, giveaways, paid posts and sad or
divisive news are dropped; quiet "vibe" posts that beat the page's normal rank first;
product posts are marked "check we stock it". Cached six hours; `&refresh=1` re-reads.
Each result has `url`, `why`, likes and a caption. To put one on the list, `POST
/api/stories` with its `url`. Swing Shack never gets Psycho Bunny.
