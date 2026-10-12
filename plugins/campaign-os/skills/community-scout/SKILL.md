---
name: community-scout
description: >-
  Find conversations on Reddit, golf forums, Facebook groups, Quora and YouTube where
  Swing Shack, Stick or Bag Drop can add something useful, and draft a comment that
  does not read as a sales pitch. Load when asked to find opportunities to join
  conversations, comment on Reddit or forums, do community engagement, social listening,
  or to revive the old Clawdia outreach agent. Drafts only: a person posts.
---

# Community scout

Revives the Clawdia brief (`tiktok-marketing/research/outreach-system.md`, daily
outputs `tiktok-marketing/research/outreach-2026-0*.md`) for all three brands, with
the two things that brief got wrong fixed. Search those files first for threads
already covered.

## Rules that do not bend

1. **Draft only.** Never post, log in, vote or DM. A person posts from the brand's
   own account after reading the draft.
2. **No pretending to be a customer.** The old samples said "I use Swing Shack in
   Randburg" in an ordinary golfer's voice. Do not write that. Every brand mention
   is either absent or disclosed ("I work with Swing Shack").
3. **Two modes per comment.**
   - `value-only` (default): answers the question fully, no brand, no link. Builds
     account history. Most comments should be this.
   - `disclosed-mention`: only when the thread asks for a place, fitter or service,
     or the rules allow it. States the affiliation in the first sentence it applies.
4. **Check the rules first.** Read the subreddit/forum rules. If self-promotion is
   banned, hostile to brands, or the thread is locked/old (>12 months), the draft is
   `value-only` or the thread is skipped. Account longevity beats a mention.
5. **Skip:** legal disputes, injuries, memes, "rate my swing" dumps, threads where
   the question is already well answered, anything about a competitor's staff.
6. **Verify the thread exists** by opening the URL. Search snippets are not proof.
   Never invent a thread, a quote or a number.

## What to look for, per brand

| Brand | Where it is | Threads worth joining |
|---|---|---|
| Swing Shack | Randburg, Johannesburg. TrackMan iO bays, fitting, lessons | simulator build/budget questions, "is a sim worth it", indoor-vs-outdoor numbers, fitting vs lessons, losing distance, TrackMan questions, where to play when it rains in Gauteng |
| Stick | Paarl, Western Cape. Fitting studio, workshop, retailer | club fitting, shafts/lie/length, iron sets, regripping and repairs, "where do I buy/fit near Cape Town", product arrival questions |
| Bag Drop | Member bag storage at the club, part of the Swing Shack ladder | lugging clubs, storing a bag, cars/commutes with clubs, "play lighter" questions, practice-habit threads |

Places: r/golf, r/Golfsimulator, r/golfclubs, r/GolfSwing, r/southafrica, r/johannesburg,
r/capetown; MyGolfSpy, GolfWRX, Golf Monthly, TalkGolf, SA golf forums and Facebook
groups; Quora; YouTube comments on SA golf channels and TrackMan/fitting videos.
South Africa first, then globally relatable threads where the advice stands alone.

## Writing the comment

Voice: a calm golfer who knows fitting and launch data. Read `brand-voice-truth`
before writing anything for Stick, and use the real feed voice, not the bible.

- Answer the actual question in the first two sentences. No warm-up, no flattery.
- Give one specific, checkable thing (a test, a number, what to measure).
- Admit limits and give the alternative, even when it is not us ("a decent
  second-hand launch monitor is fine for tempo work").
- If a mention is warranted: one disclosed sentence, no link unless asked, no CTA.
- Never: "book now", "we can help", "contact us", urgency, discount codes, emojis,
  em dashes, repeating the same comment across threads.
- Different thread, different comment. Reddit detects copy-paste.

## Output

One block per opportunity, ranked, 5-8 per brand per run. If nothing suitable:
"No suitable posts found." Save to `research/community-scout-YYYY-MM-DD.md`.

```
Brand:
Platform / community:
Thread title:
Link (opened and checked):
Age / comment count:
Why it is worth joining:
Rules check: (self-promo allowed? thread open? brand-hostile?)
Mode: value-only | disclosed-mention
Draft comment:
Why this will not read as a pitch:
Approved by / posted by / date: (left blank)
```

## How to search (what works)

- The built-in `WebSearch` is US-only and ignores recency; it returns articles, not
  threads. Use it only to discover communities.
- For threads, use the connected browser on `reddit.com/r/<sub>/search/?q=...&sort=new&t=year`
  and each forum's own search. Read the page text, do not scrape at volume.
- Reddit's public JSON endpoints return 429 (why `reddit_trends` was disabled
  2026-09-18). A scheduled job needs Reddit's official OAuth API credentials, which
  Christelle must create; none are on file.
- Log opened threads to avoid re-suggesting them.

## Triage rules for F5Bot emails

F5Bot emails a link and snippet for each keyword hit on Reddit. Open the thread (or work
from the pasted text) and decide pass or skip.

**Pass (draft a comment) when all are true:**
1. A person asks a question or describes a real problem (distance loss, fitting, sim vs
   course, building or buying a sim, where to get fitted, storing or carrying clubs).
2. Under 12 months old, thread open, and under about 40 comments so a reply is seen.
3. We can add something specific that is not already said in the replies.
4. South Africa first (r/southafrica, r/johannesburg, r/capetown, local wording like
   "rand", "Gauteng", "Paarl"); otherwise only if the advice stands alone anywhere.
5. The community allows it: read the rules. Self-promotion banned, or hostile to brands:
   value-only comment, no mention.

**Mention the brand (disclosed) only when** the poster asks for a place, fitter or
service in our area. First sentence says "I work with <brand>". No link unless asked.

**Skip when any are true:**
- Keyword is a false match (a person named Stick, "bag drop" at an airport, "swing shack" as a place elsewhere).
- Memes, rage posts, politics, LIV or tour gossip, injuries, legal or refund disputes.
- "Rate my swing" video dumps or sale listings.
- A competitor is being discussed by name and we would be correcting or attacking them.
- Already answered well, locked, or older than 12 months.
- Poster is a minor.
- The only thing we could say is a pitch.

**Output per email:** Pass or Skip, the one-line reason, and for Pass the drafted comment
in the standard format. Report counts at the top ("12 emails: 3 pass, 9 skip") so noisy
keywords can be dropped from F5Bot.
