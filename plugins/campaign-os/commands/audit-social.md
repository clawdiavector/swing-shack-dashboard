---
description: Pull a brand's whole Instagram catalogue with insights and full-res images
allowed-tools: Bash(python3 campaign-os/scripts/audit_social.py:*), Bash(python3 -c:*), Read, Grep
argument-hint: "<brand> [--no-images] [--max-pages N]"
---

## Why this exists

The brand bibles drift from the real feed. Stick's tagline "Better begins here."
closes 173 of 261 captions and appears in no brand file; the bible is entirely
fitting and TrackMan while 39% of posts are product arrivals. The audit output is
the source of real voice — prefer it over the copy bible when they disagree.

## Run it

```bash
python3 campaign-os/scripts/audit_social.py stick
```

Replace `stick` with `$1` when a brand is given. `--no-images` skips the
full-resolution downloads; `--max-pages N` caps paging.

Writes `data/brand-directory/<brand>/feedback/instagram-audit.json` and
`images/posts/<id>.jpg`.

## Before you run

**Do not scrape Instagram HTML.** Logged out it yields 12 posts as 640px
centre-crops, and the `oh=` signature covers the transform, so the URLs cannot
be rewritten for full resolution. An hour went into scraping on 2026-10-05 while
`_lib/meta_api.py` sat unused. This script walks `paging.next` to the end through
the Graph API and gets the real thing.

Credentials resolve per brand from `data/integrations/<brand>/instagram.json`
via its `credential_env`. If the script exits saying there is no token, that file
needs `ig_business_account_id` and `credential_env` filled in and the named
variable exported — report that rather than working around it.

## Reading the output

Check the **insights coverage** table first. A media type showing `0/N` means its
metric set is wrong, not that those posts had no engagement — that exact failure
silently blanked 130 of Stick's 261 posts when every media type was sent the
image metric set. `METRICS_BY_MEDIA_TYPE` in the script holds one set per type
and narrows the request until the API accepts it.

Then look at:
- `by_media_type` — how much of the feed is reels versus static. Shapes what is
  worth templating.
- the top-10 by interactions printed at the end — what actually works.
- caption endings and recurring phrases — the real voice, versus the bible.

## After a run

Summarise what the feed says that the brand files do not, and write genuinely new
voice findings into `feedback/`. Do not edit the copy bible to match the feed
without asking — the gap between them is information.
