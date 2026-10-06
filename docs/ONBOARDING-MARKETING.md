# Onboarding a marketer onto Campaign OS

Getting a second person's Claude Code to do what Kyle's does. Written for
Christelle, 2026-10-06; good for anyone joining the marketing side.

The split to keep in your head: **the repo carries the code and the brand data; the
plugin carries the knowledge.** You need both, and you work with the repo as your
working directory.

---

## Part 1 — Setup (once, ~10 minutes)

### 1. Clone the repo

```bash
git clone https://github.com/clawdiavector/swing-shack-dashboard.git
```

Needs access to the `clawdiavector` org — ask Kyle if the clone 404s.

### 2. Install the Python dependencies

Both files. The root one runs the Flask app; the `campaign-os/` one carries
**Pillow**, which the post composer needs — install only the root file and
`/render-post` fails on import.

```bash
pip install -r requirements.txt -r campaign-os/requirements.txt
```

### 3. Install the plugin

From inside the clone, in Claude Code:

```
/plugin marketplace add .
```

```
/plugin install campaign-os@campaign-os
```

Restart Claude Code. Confirm it took by typing `/` — you should see
`/audit-social`, `/render-post`, `/schedule-post` and `/verify-specs`.

### 4. Set the environment

Put these in your shell profile. `DATA_DIR` is the one that matters most: it is the
runtime truth directory, and pointing it at a scratch path is what keeps local
experiments away from anything real.

```bash
export DATA_DIR="$HOME/.campaign-os-local"     # scratch; never the repo's data/
export COS_JOB_TOKEN="ask-kyle"                # job endpoints
export KREA_API_KEY="your-own-krea-key"        # image generation
```

Credentials Kyle has to hand over or provision for you — none of these are in git,
by design:

| Variable | For | Notes |
|---|---|---|
| `COS_JOB_TOKEN` | `/api/jobs/*` and part of `/api/ops/*` | Shared secret |
| `KREA_API_KEY` | Krea image generation | **Get your own** — credits are per-account |
| `META_SYSTEM_USER_TOKEN` | `/audit-social` Instagram pulls | Plus `META_PAGE_ID`, `META_INSTAGRAM_BUSINESS_ACCOUNT_ID` |
| Campaign OS login | `/ops/*` and the Review queue in prod | Session cookie, not a bearer token |

### 5. Pull the brand imagery

**Raw images are not in git.** Google Drive is the source of truth, and the repo
holds only text, templates and golden renders. Without this step the composer has
no photography to place.

```bash
python3 campaign-os/scripts/ingest_public_drive_folder.py
```

Ask Kyle for the share link and the two per-brand ingest roots — the script's
constants are the *children* only, which is a trap worth knowing about up front.

### 6. Prove it works

```
/verify-specs
```

Free, generates nothing, spends nothing, and probes live. If it runs and reports,
the install is good. It also happens to be the single most useful command in the
set — see Part 3.

---

## Part 2 — The prompts to actually give Claude

Paste these. They are shaped to trip the right skills; the point of each one is in
the line underneath.

### Starting any session

> Load the campaign-os-map skill, then tell me what already exists for what I'm
> about to do.

*The repo looks sparse and is not — 109 lib modules, a 2,700-line retrieval engine,
a deterministic composer, 13 measured templates. A full day was once lost rebuilding
something that already shipped. This is the cheapest habit in the whole workflow.*

### Making a post (the main loop)

> Show me every post template we have measured, for all brands.

*Runs `/render-post --list`. Always the first move — the layout you want may already
be a template, in which case you are 200ms and zero credits from done.*

> Render the <archetype> template for <brand> with headline "<text>" and this photo,
> then show it to me.

*Deterministic. Correct text, on-palette, free.*

> Now schedule it for <date> with a caption in Stick's real voice, and put it in the
> Review queue.

*The step people skip. A rendered PNG sitting on disk shows up **nowhere** in the UI
— that mistake cost a full round trip on 2026-10-05. "Review queue" is what makes it
a post a human can approve.*

### Writing copy that sounds like the brand

> Read data/brand-directory/stick/feedback/instagram-audit.json and write me five
> captions in the voice that's actually in the feed, not the voice in the bible.

*The brand bibles drift. Stick's real tagline "Better begins here." closes 173 of 261
captions and appears in **no** brand file; the bible is entirely fitting and TrackMan
while 39% of posts are product arrivals. When the audit and the bible disagree, the
audit wins.*

> Re-run the Instagram audit for <brand> so we're working off current numbers.

*Runs `/audit-social <brand>`.*

### When you genuinely need a new image

> Load krea-lab, confirm the model id and the accepted resolutions, then generate.

*Never guess a model id or a size. Guessing cost three prod deploys, three one-shot
slots and a lost day on 2026-10-05 — and the answer was still wrong. Looking it up
costs four minutes and zero credits. One spec probe later found the one-shot path
routing to `ideogram/ideogram-4`, a model that does not exist upstream.*

> That one worked — measure it into a template so we never have to generate it again.

*Loads `campaign-os-template`. This is how a Krea win graduates down into something
deterministic, and it is the single highest-leverage thing you can do after a good
generation.*

### A new post style arrives

> Here are six example posts from <brand>. Turn them into a Campaign OS template.

*`campaign-os-template` groups by filename, maps platforms, measures layout, fonts
and colours, extracts the logo, writes the archetype JSON, renders and diffs against
the references.*

---

## Part 3 — The four things that bite everyone

**1. Verify before you trust.** Specs here drift from reality silently and nothing
checks. Six were found wrong in a single day by probing live. Before relying on a
model id, a resolution, a scrim value or a template cap:

```
/verify-specs
```

Every check is free.

**2. `data/` is read-only.** Human-committed seed data. No automation writes it,
ever. Runtime truth lives in `$DATA_DIR`.

**3. Never push `main`.** It auto-deploys to Railway the moment it lands. Program
work goes on a branch and Kyle merges it. Claude is instructed not to push `main`
without Kyle approving it in the same message — don't talk it out of that.

**4. Deterministic beats generated.** Nothing should run at a higher tier than its
uncertainty requires: **lab → script → job → agent**. If the layout is known,
render it.

---

## What Christelle does not get, and why

Not withheld — just physically Kyle's desk:

- **The Hermes agent fleet and scheduled jobs.** 34 profiles on a Mac Mini reached
  over a Tailscale bridge. The `campaign-os` skill's `agents.md`, `hosts.md` and
  `mac-build-deploy.md` modules describe that machine and are marked inline.
- **The `agent-control` foreman repo.** A separate repo. Where a module needs it, the
  bearer `curl` recipes in `api.md` are the portable equivalent.
- **Railway CLI.** Mac only. Prod deploys from GitHub anyway.

Everything in Part 2 runs on any machine with the repo and the credentials.
