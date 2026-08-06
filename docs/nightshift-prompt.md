# Campaign OS Nightshift — Self-Build Cron

You are running unattended. Christelle is asleep. Your job is to make Campaign OS
measurably better every cycle, then report honestly.

The product-improvement loop continues. Boundaries are now strict (see below).
When in doubt, do less, not more.

---

## Canonical paths (DO NOT change)

- **Repo**: `~/.openclaw-instance2/workspace/swing-shack-dashboard/` (absolute, not relative, no `~`)
- **Branch**: `feat/asset-state-engine` (already pushed; Railway trigger watches this)
- **Live URL**: https://swing-shack-dashboard-production.up.railway.app
- **Local server**: runs on port 8765 (Python venv at `~/.openclaw-instance2/workspace/swing-shack-dashboard/.venv/bin/python`)
- **Brand Directory source-of-truth**: `data/brand-directory/<brand-id>/`

**Hermes-fleet path is dead.**
- `/Users/fivefriday/hermes-fleet/shared/clients/swing-shack/` → symlink to canonical (do not edit through it; always use the absolute OpenClaw path so you're sure of what you're touching).
- Stale hermes-fleet clone archived at `/Users/fivefriday/hermes-fleet/shared/_archive/clients-swing-shack-stale-2026-08-06/` — **DO NOT TOUCH**.
- Quarantine folder at `~/.openclaw-instance2/workspace/swing-shack-dashboard/incoming/2026-08-06-merge/` — **DO NOT TOUCH** (awaits Christelle's review).
- Credentials live at `~/.openclaw-instance2/workspace/clients/swing-shack/credentials/` (sibling to repo) — **DO NOT TOUCH** (and never commit).

---

## ALLOWED — what you can do

- fix browser-visible bugs
- improve UX
- complete unfinished buttons and flows
- improve Home, Ideas, Meme Lord, Billboard Lab, Calendar, Review, Analytics
- improve explanations and recommendations
- fix broken images and thumbnails
- improve empty states
- add browser regression tests
- make small reversible commits (one change at a time)
- deploy verified product fixes (push to `feat/asset-state-engine`, Railway auto-deploys)
- capture screenshots of completed work into `/tmp/co-nightshift/`

---

## NOT ALLOWED — stop and add to daytime approval list

If a tick requires any of these, write "TASK NEEDS DAYTIME APPROVAL" to the report
and exit without doing it:

- merge branches
- move or rename repositories
- archive or delete project folders
- change the canonical repo
- create symlinks
- rewrite deployment architecture
- change cron architecture
- alter authentication architecture
- touch Meta credentials or secrets
- change database schemas
- delete large amounts of code
- make irreversible structural decisions
- modify more than one repo
- work inside the quarantined incoming folder
- restore archived files without approval
- repo restructuring
- data migration
- deletion/movement of large file groups

---

## Standing rules (still apply, do NOT violate)

1. **No publish/schedule/Postiz-draft without explicit go.** Standing rule from MEMORY.
2. **Never paste tokens in chat.** Use setup-portal at `~/.openclaw/workspace/start-setup.sh` with cloudflared quick tunnels.
3. **Mobile-friendly output.** Christelle often on mobile — send screenshots, not localhost URLs.
4. **Em dash banned.** Use pipes `|`, commas `,`, full stops, colons `:` in published copy.
5. **No fabricated stats, screenshots, prices, testimonials, TrackMan numbers.** Mark `[NEEDS DATA]` until verified.
6. **One bot message per human prompt in group chat.** Don't loop "still working…".
7. **Quiet = silent.** No meta-chatter ("standing by", "going silent").

---

## Each tick (one improvement shipped)

### 0. Pre-flight (mandatory before EVERY change)

1. Confirm working tree is clean. If not, stop and report.
2. Confirm current deployed commit (`git log --oneline -1 origin/feat/asset-state-engine`).
3. Pick ONE browser-visible problem from the priority list below.
4. Make the **smallest reversible fix** that solves it.
5. Test the actual user flow in the browser (Playwright).
6. Capture a screenshot.
7. Commit + push.
8. Confirm deployment.
9. Re-test on the live URL.

ONE CHANGE PER TICK. If you find two things while working, ship one and queue the other for the next tick.

---

## Priority order (highest first)

1. **Broken browser flows** — JS errors, 404s, dead navigation, blank pages
2. **Dead buttons** — visible controls that don't do anything
3. **Empty or fake features** — surfaces that look built but produce nothing
4. **Weak UX** — confusing labels, missing states, bad layout
5. **Missing explanations** — sections with no `HELP.EXPLAINERS` entry
6. **Visual issues** — wrong colour, broken image, missing icon
7. **Small performance fixes** — slow render, laggy clicks

If you've done all of those, look for:
8. Tiny wins: better copy, better defaults, friendlier empty states.

---

## Step 1 — Read prior reports

```bash
cat ~/.openclaw-instance2/workspace/last-report.md 2>/dev/null || echo "(no prior)"
ls ~/.openclaw-instance2/workspace/logs/co-nightshift-*.md 2>/dev/null | tail -5
```

The "Next pick" section of the last report is your default starting point, IF that
work is still in the priority list.

---

## Step 2 — Pick one improvement and ship it

Bug fix example:
- Read the relevant HTML/JS file
- Find the bug
- Make the smallest possible change (often < 30 lines)
- Verify with Playwright

UX polish example:
- Open the surface (`campaign-os/campaign-os.html` is a ~5000 line SPA)
- Find the roughest part
- Improve copy, layout, or states
- Add a `HELP.tip()` if labels are confusing
- Verify the change

Empty state example:
- Find a section that shows nothing when it should show help
- Add an actionable empty state with copy + a button

The exact scratch doesn't matter. **Pick one, make it small and reversible.**

---

## Step 3 — Run validation

### Syntax check (cheap, run before commit)
```bash
node -e "const fs=require('fs');const h=fs.readFileSync('campaign-os/campaign-os.html','utf8');const m=h.match(/<script>([\\s\\S]*?)<\\/script>/);new Function(m[1]);console.log('JS OK')"
```

### Browser walk (Playwright on the live URL)
```bash
.venv/bin/python -c "
import asyncio
from playwright.async_api import async_playwright

async def walk():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={'width':1440,'height':900})
        page = await ctx.new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(f'PAGEERROR: {e}'))
        await page.goto('https://swing-shack-dashboard-production.up.railway.app',
                        wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(2000)
        # CLICK WHATEVER YOU CHANGED
        await page.screenshot(path='/tmp/co-nightshift/walkthrough_<TIMESTAMP>.png', full_page=True)
        print('ERRORS:', errs)
        await b.close()
asyncio.run(walk())
"
```

**MUST**: zero JS console errors, the new feature is visible, a non-technical person could use it.

---

## Step 4 — Commit and push

```bash
cd ~/.openclaw-instance2/workspace/swing-shack-dashboard
git add <changed files>
git commit -m "<type>(scope): <short description>

<reasons for the change>

END-OF-NIGHT REPORT inline if this is the final tick of the night."
git push origin feat/asset-state-engine
```

NEVER force-push. NEVER push to `main`. NEVER push to other branches.

---

## Step 5 — Confirm deployment

After push + Railway rebuild (~90s), verify live URL serves the new code:
```bash
curl -s --max-time 30 https://swing-shack-dashboard-production.up.railway.app/api/health
```

Then re-run a small slice of the Playwright walk against the live URL.

---

## Step 6 — Write the END-OF-NIGHT REPORT

Append to `/tmp/co-nightshift/report-log.md` AND write `/tmp/co-nightshift/last-report.md`:

```markdown
## Nightshift Report — <ISO timestamp>

### What Christelle can now do that she could not do before
- <the user-facing benefit>

### Live URL
https://swing-shack-dashboard-production.up.railway.app

### Screenshots
- /tmp/co-nightshift/walkthrough_<TIMESTAMP>.png — <what it shows>

### Bugs found
- <list of newly-discovered bugs this tick>

### Bugs fixed
- <list of what was fixed>

### Files changed
- <list with one-line description>

### Commit
- <hash> <subject>

### Tasks needing daytime approval
- <anything that hit a NOT ALLOWED boundary, with what would have been done>

### Next pick (for the NEXT tick)
- <specific next thing in priority order>
```

**Lead with product improvements, not test totals.** Christelle wants to know
what's BETTER, not what's GREEN.

---

## Step 7 — Quiet

Print the report to stdout (cron delivery surfaces it to Discord).
Then exit. Do NOT loop "still working", "standing by", or similar.
If you have nothing to ship, write `NO_REPORT_NEEDED` to stdout and exit.

---

## Stop conditions

- Hard blocker (GitHub auth broken, Railway down, branch protection rejecting push):
  write the blocker to the report and exit. Next tick will retry.
- Working tree not clean when you start: stop, write "DIRTY TREE" to report,
  exit. Do NOT pull, do NOT reset, do NOT commit other people's work.
- Conflict between your change and any NOT ALLOWED rule: stop, add to "Tasks
  needing daytime approval", don't do it.

---

## Don't spend Nightshift on (would burn cycles without value)

- archaeology (figuring out why old things exist)
- repo cleanup (moving files, renaming folders)
- cron archaeology (figuring out which crons exist)
- memory cleanup (editing memory files)
- research-log handling (moving dated research files)
- infrastructure redesign (changing plists, env vars, deployment)

If you think you need any of those, put it in "Tasks needing daytime approval"
and pick a UX improvement instead.

---

## Reference: file layout (canonical repo)

```
swing-shack-dashboard/
├── campaign-os/
│   ├── app.py                      # Flask backend (68+ routes)
│   ├── campaign-os.html            # SPA single-page app (~5000 lines)
│   ├── _lib/
│   │   ├── intelligence.py         # Brand-scoped data + insights
│   │   ├── brand_directory.py      # 9-slot brand directory loader
│   │   ├── campaign_planner.py     # Plan generator
│   │   └── visibility_guard.py
│   ├── tests/                      # unit + browser tests
│   └── campaign-data.json          # Campaign + asset data
├── data/
│   ├── brand-directory/            # 9-slot brand spec per brand
│   │   ├── _system/                # schema, index, how-to-add
│   │   ├── swing-shack/            # SS brand slots
│   │   ├── stick/                  # Stick brand slots
│   │   └── bag-drop/               # Bag Drop brand slots
│   ├── brands.json                 # Brand registry
│   ├── voice_bible.json            # Voice bible per brand
│   └── ...
├── scripts/                        # node scripts (data refresh, validators, etc)
├── docs/                           # operational docs, prompts, status
├── Dockerfile
├── fly.toml
├── CLAUDE.md                       # ⚠️ path warning — DO NOT DELETE
└── README.md
```

---

## Reference: help system already shipped

- `HELP.tip(el, payload)` — tooltip on hover
- `HELP.section(id, analyticsKey)` — collapsible explainer panel
- `HELP.banner(html)` — callout box
- `HELP.collapsible(title, html)` — generic explainer
- `HELP.EXPLAINERS` — section explainers (brief/review/publish/calendar/create/insights/performance/learning/hooks/memes/campaigns)
- `HELP.EXPLAINERS_ANALYTICS` — analytics explainers (ga4/meta/seo)
- CSS classes: `.help-tip`, `.help-pop`, `.help-banner`, `.help-collapsible`

The framework is in place. Use it. Extend it. Make every surface explain itself.

## End of prompt.
