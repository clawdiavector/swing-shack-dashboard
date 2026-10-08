---
name: the-algorithm
description: >-
  Musk's five-step method for Campaign OS work — question the requirement, delete,
  simplify, accelerate, and only then automate. Loading it switches on two light
  hooks for the rest of the session. Load when asked to build, add, automate or
  schedule something in Campaign OS, when asked to run the algorithm on an existing
  job, script or process, or when someone types /the-algorithm.
argument-hint: "[off | on | <thing to run it on>]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/the-algorithm/hook.py" *)
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: python3 "${CLAUDE_PLUGIN_ROOT}/skills/the-algorithm/hook.py" remind || true
  PreToolUse:
    - matcher: "Write"
      hooks:
        - type: command
          command: python3 "${CLAUDE_PLUGIN_ROOT}/skills/the-algorithm/hook.py" gate || true
---

# The algorithm

Arguments: `$ARGUMENTS`

- **`off`** — run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/the-algorithm/hook.py" off ${CLAUDE_SESSION_ID}`, say
  it's off, stop. **`on`** — the same with `on`.
- **Anything else** — run the five steps on that thing (an existing job, script,
  template or process). Deleting things that already exist is where the method pays
  most.
- **Empty** — say the algorithm is on for this session, then apply it to whatever
  comes next.

While on, the hooks do two things and nothing else: one line of context on each
prompt, and a one-time challenge the first time you create a **new** file under
`campaign-os/_lib/`, `campaign-os/scripts/` or `plugins/campaign-os/`. Answer it in
chat, retry, and the write goes through. Edits are never gated. Off for the session
with `/the-algorithm off`; a new session starts with it off until the skill loads again.

## The steps — in order, and say which one you are on

**1. Question the requirement.** Every requirement carries a person's name — Kyle or
Christelle — not "marketing" or "the spec". No name: ask, don't build. Then ask if
it's true at all. Specs here drift silently; six were wrong in one day. A brand
bible saying Stick is all fitting and TrackMan is a requirement; the feed being 39%
product arrivals is the fact. Put `Requirement-Owner: <name>` in the commit.

**2. Delete.** Before adding, find what to remove or reuse.
- Load `campaign-os-map`. It probably exists — on 2026-10-05 a day went into
  rebuilding a poster an existing template already rendered.
- Can a step, field, flag, job or file go entirely?
- Delete enough that roughly one in ten deletions has to come back. If nothing ever
  comes back, you are not deleting enough. Say in the commit what you deleted.

**3. Simplify** what survived — fewer moving parts, one path instead of two. Not
before step 2: optimising something that should not exist is the classic waste.

**4. Accelerate** — shorten the loop. A 200ms deterministic render beats a Krea
round-trip; a free probe (`/verify-specs`) beats a credit-spending test.

**5. Automate — last.** Climb only as high as the uncertainty demands:
**lab → script → job → Hermes agent.** Automating a process that steps 1–4 would
have cut just does the wrong thing faster.

## Report it

When the work is done, one short block:

```
Owner:      Kyle
Deleted:    <what went, or "nothing — <why not>">
Simplified: <…>
Faster:     <…>
Automated:  <tier, or "not yet — still a lab">
```
