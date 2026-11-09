# Review pack: a no-login page where a client approves, comments and uploads

Built 2026-11-03 for Chantalle (MCM, a separate client who cannot sign in to Claude).
Requirement owner: Christelle. Code: `campaign-os/_lib/review_pack.py`, routes in `app.py`
(search `Review pack`), tests `tests/test_review_pack_20261103.py` and
`tests/test_review_pack_choice_20261103.py`.

## What it is

A **pack** is a folder of **items** (a post, a carousel, a design with options A, B and C)
kept in `DATA_DIR/review-packs/<id>/` (never in git). Each pack gets a signed link that
lasts 30 days. The client opens `/review-pack/<token>` with no login and can, per item:

- pick a design (A, B or C), which does **not** approve the post;
- **Approve / Reject / Hold**;
- see "6 of 20 answered" at the bottom with a **Next post** button that jumps to the first unanswered one;
- press **I'm done** at the end (a note for us, see below);
- comment, tagged *general*, *copy edit* or *design edit*;
- upload her own photos (images only, up to 20 per go, 10 MB each), with where it came from
  and a permission tick.

**Approve and Reject only record a decision.** Nothing here schedules, sends or posts, and
`review_pack.py` imports nothing that could.

## Our side (bearer `COS_JOB_TOKEN`, under `/api/jobs/review-packs`)

```
POST /api/jobs/review-packs                         {title, client, theme, items:[{id,title,kind,caption,channels,when,audience,note}]}
POST /api/jobs/review-packs/<id>/items                {id,title,kind,caption,channels,when,audience,note}  add a post to a live pack (same links, answers untouched)
POST /api/jobs/review-packs/<id>/items/<item>/image  multipart "file"   (?replace=1 swaps the pictures and clears that item's decision)
POST /api/jobs/review-packs/<id>/share              {who}  -> share_url
GET  /api/jobs/review-packs/<id>                    decisions, comments (both sides), uploads
POST /api/jobs/review-packs/<id>/reply              {item, text, tag, who}  (shows to her as "us")
GET  /api/jobs/review-packs/<id>/file/<name>        one of her uploads (bearer)
GET  /api/jobs/review-packs/                        list
DELETE /api/jobs/review-packs/<id>                  delete for good (409 once she has answered it; ?force=1 overrides)
GET  /api/jobs/review-packs/<id>/news?since=<time>   what she did after <time>: counts + plain text, empty when nothing; sends nothing
```

`kind` is `single`, `choice` (A/B/C, needs 2 or 3 pictures), `carousel` or `note`.
`theme` is optional: `{name, ink, bg, accent, gradient:[3 hex colours]}`.

## Telling us when she answers

`/news` is the same shape as the morning message: plain `text` plus `counts`, nothing sent by the
app. Keep the `now` from each reply and pass it as `since` next time, so each answer is reported
once. The Mac watcher (15-minute poll, no agent) calls it and sends Telegram only when `empty` is
false. That Mac step is Kyle's; it is not wired yet.

## "I'm done"

`POST /review-pack/<token>/done` records that this person has finished (`done.json`, one row per person,
pressing again just updates the time). It is a note for us and nothing more: nothing is scheduled or
sent. It shows in `/news` as `done: ["Chantalle"]` and a line "Chantalle says they are done", so the
watcher can ping. It counts as the client having answered, so deleting the pack is refused. If posts
still have no answer the button asks once more ("Send anyway") before recording. Notes (`kind: note`)
are not counted in "answered".

## Who can see what

- **Anyone holding a pack link** sees everything on that pack: every decision, comment of hers and
  ours, and upload. They can also act (approve, comment, upload). There is no view-only link yet.
- Mint one link per person with `/share {who}` so their name is on what they do. Links last 30 days
  and are scoped to one pack.
- **Colours:** each person's comments, decisions and uploads carry their own colour (a bar and their name), kept per pack in `people.json`. 'Yolanda' and 'yolanda ' are one person; ten colours before any repeat.
- **Our side** (the API above) needs the job token. No login page lists packs yet.

## Safety notes

- The link is signed with the app secret, scoped to one pack, and refused if the pack is gone.
  Herman's calendar link cannot open a pack and the reverse.
- Uploads are checked by decoding the bytes (never the file name), re-encoded (drops hidden
  location data), saved under a random name, and served only with the link.
- **The gate lets any URL ending in .png/.jpg/.css/.js etc. through without a login check**
  (the static-asset rule in `_gate()`). The review-pack branch in `_gate()` runs before that
  rule, and our two bearer file routes check the token themselves. Worth knowing for any new
  route whose path ends in a file extension.
- Per-link rate limits on act, comment and upload on top of the app's general limiter.

## Catalog (2026-11-09, slice c2-catalog)

A **catalog** is a review pack tied to one campaign plan (`kind: "catalog"`). Each post and
story step becomes a slot; shoot, boost and reminder steps are left out. Slots show
**Picture to come** until a picture is added. The pack stays in sync with the plan; decisions,
comments and uploads are never cleared by sync.

**Our side (signed in):**

```
POST /api/plan/v1/<brand>/<plan_id>/catalog     ensure + sync → {pack_id, url, counts}
GET  /catalog/<pack_id>                         sync, then redirect to /review-pack/<token> (staff mode on)
GET  /api/review-packs                          list packs (id, title, kind, plan_id, brand, counts)
POST /api/review-packs/<pack_id>/share          {who} → guest share_url (session; same shape as the job route)
```

Indexed at `DATA_DIR/review-packs/_catalog_index.json` (`brand:plan_id` → `pack_id`).
Code: `campaign-os/_lib/catalog.py`, tests `campaign-os/tests/test_catalog_c2_catalog_20261109.py`.

## Not built yet

A page on our side listing packs and live decisions (today: the API above), email or
Telegram pings when she acts, an Afrikaans page.
