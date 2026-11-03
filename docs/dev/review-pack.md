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
- comment, tagged *general*, *copy edit* or *design edit*;
- upload her own photos (images only, up to 20 per go, 10 MB each), with where it came from
  and a permission tick.

**Approve and Reject only record a decision.** Nothing here schedules, sends or posts, and
`review_pack.py` imports nothing that could.

## Our side (bearer `COS_JOB_TOKEN`, under `/api/jobs/review-packs`)

```
POST /api/jobs/review-packs                         {title, client, theme, items:[{id,title,kind,caption,channels,when,audience,note}]}
POST /api/jobs/review-packs/<id>/items/<item>/image  multipart "file"   (?replace=1 swaps the pictures and clears that item's decision)
POST /api/jobs/review-packs/<id>/share              {who}  -> share_url
GET  /api/jobs/review-packs/<id>                    decisions, comments (both sides), uploads
POST /api/jobs/review-packs/<id>/reply              {item, text, tag, who}  (shows to her as "us")
GET  /api/jobs/review-packs/<id>/file/<name>        one of her uploads (bearer)
GET  /api/jobs/review-packs/                        list
DELETE /api/jobs/review-packs/<id>                  delete for good (409 once she has answered it; ?force=1 overrides)
```

`kind` is `single`, `choice` (A/B/C, needs 2 or 3 pictures), `carousel` or `note`.
`theme` is optional: `{name, ink, bg, accent, gradient:[3 hex colours]}`.

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

## Not built yet

A page on our side listing packs and live decisions (today: the API above), email or
Telegram pings when she acts, an Afrikaans page.
