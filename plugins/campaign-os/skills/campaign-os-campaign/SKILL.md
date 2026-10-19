---
name: campaign-os-campaign
description: >
  Kyle said set up / create a campaign / TEST n / Suggest Date / Brief.
  Never load this for lodging a post, a story link, or a calendar moment.
---

# Suggest Date (named window + Brief)

The only legal move is the script below. It POSTs a **candidate** (Waiting
for you). Then stop.

Do not curl extra. Do not upsert. Do not enqueue caption or image. Do not
approve onto Main Calendar. Do not open `operator-post`. Do not write seed
JSON. Do not ask channel, story vs post, or how many posts.

## Ask once if missing

Brand (Swing Shack / Stick / Bag Drop). Stop if still empty.

Fitting = golf club fitting (`ss-fitting` / `stick-fitting`). “Off the rack is
for groceries” is Swing Shack humour — put it in `--why`, not a new brand.

## Run

```bash
python3 "$HOME/.agents/skills/campaign-os-campaign/suggest_campaign.py" \
  --brand swing-shack \
  --title "TEST 2" \
  --start 2026-10-24 \
  --end 2026-10-24 \
  --pillar fitting \
  --why "Push fittings with a humorous angle. Off-the-rack is for groceries."
```

Paste stdout back. That is the job. Candidate only — Kyle still taps Add to
calendar. Needs `COS_JOB_TOKEN` (never print it).
