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
