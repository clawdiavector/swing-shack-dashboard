---
name: campaign-os-mail
description: Email a teammate from your own agent inbox (AgentMail) so the manual "hey, I added X, check it out" step disappears. Load when the user says "email Kyle/Christelle/Herman", "let them know", "tell her/him", "send an update", or when a PR needs review or a skill, template, framework or plugin update ships. Also load to set up your own sender inbox.
---

# Campaign OS agent mail

Each person has **their own** AgentMail inbox and API key. Your Claude sends from your inbox; replies go to your real email. The shared **contact list** (`contacts.json`, next to this file) says who is who and where mail goes.

Script (Python 3, stdlib only): `${CLAUDE_SKILL_DIR}/scripts/cos_mail.py` (use `python`, `python3` or `py` depending on the machine).

## First: check it works
```
python cos_mail.py status        # prints READY or what is missing
```
Not READY, or the person has no inbox yet -> follow `SETUP.md` and walk them through it step by step. Do not guess keys.

## Send
Always dry-run first and show the draft; add `--send` only once the person says send (an explicit "email her about X" is the go-ahead for that one message).
```
python cos_mail.py tell christelle --kind skill --subject "New Stick template" \
  --message "I added a venue post template. Renders in 200ms." \
  --link <PR or wiki URL> --how-to "Update the plugin, restart Claude Code"
```
Kinds: `update | review | skill | package | template | framework | question`.

## When to send (and when not)
Send when something changed that the other person has to *do or know*:
- A PR needs their review -> `review` (link the PR, say what to check).
- A new/changed skill, template, framework or command -> `skill|template|framework`.
- The plugin has a new version they must pull -> `package` (how-to: `claude plugin marketplace update campaign-os && claude plugin update campaign-os@campaign-os`, then restart).
- A wiki page they should read -> `update` (how-to: open the page path).
- You need a decision or are blocked -> `question`.

Do **not** send: for every commit, anything the person already saw live, secrets or tokens, or to anyone not in the contact list. One mail per change-set, not a stream.

## Writing the mail
2-4 sentences, plain language: what changed, why they care, **one** action (`--how-to`). No ticket ids, no internal jargon, no keys.

## Contacts
```
python cos_mail.py contacts                       # who is who
python cos_mail.py set-email christelle me@x.com  # fill your own blank entry
```
Roles and "what to tell them" are in `contacts.json`. To add someone (Herman, anyone), add an entry there with a role and email, commit and push so everyone's Claude sees it. Kyle M is the developer; Christelle is marketing.
