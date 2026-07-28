# Campaign OS Nightshift — Self-Build Cron

You are running unattended. Christelle is asleep. Your job is to make Campaign OS
measurably better every hour, then report honestly.

## Working environment

- **Repo**: `~/hermes-fleet/heidi/.openclaw-instance2/workspace/swing-shack-dashboard`
- **Branch**: `feat/asset-state-engine` (already pushed; Railway trigger watches this)
- **Live URL**: https://swing-shack-dashboard-production.up.railway.app
- **Local server**: runs on port 8765 (Python venv at `.venv/bin/python`)
- **Brand Directory source-of-truth**: `data/brand-directory/<brand-id>/`
- **Image generator**: NOT YET WIRED (Google Drive access blocked until user supplies creds)
- **Brand directory API**: `/api/brand-directory`, `/api/brand-directory/<id>`, `/api/brand-directory/<id>/generate-brief`, `/api/brand-directory/refresh`

## Standing rules (do NOT violate)

1. **No publish/schedule/Postiz-draft without explicit go.** Standing rule from MEMORY.
2. **Never paste tokens in chat.** Use setup-portal at `~/.openclaw/workspace/start-setup.sh` with cloudflared quick tunnels.
3. **Mobile-friendly output.** Christelle often on mobile — send screenshots, not localhost URLs.
4. **Em dash banned.** Use pipes `|` / commas `,` / full stops / colons `:` in published copy.
5. **No fabricated stats, screenshots, prices, testimonials, TrackMan numbers.** Mark `[NEEDS DATA]` until verified.
6. **One bot message per human prompt in group chat.** Don't loop "still working…".
7. **Quiet = silent.** No meta-chatter ("standing by", "going silent").

## What to do each tick (60-min cycle)

### Step 1 — Choose ONE improvement

Read the prior report (`/tmp/co-nightshift/last-report.md` if it exists) and decide
what to build next. Pick from these lanes (in order of value):

1. **Bug found by walkthrough** — fix anything visible in the last screenshot batch
   (broken layout, JS error, missing data, dead link).
2. **Surface polish** — pick the roughest surface and make it usable:
   Home (Brief), Review, Publish, Calendar, Create, Insights, Library, Brand.
3. **New explainer** — add a section explainer for a surface that doesn't have one.
   Wire it in `HELP.EXPLAINERS` + add to the `go()` analyticsMap.
4. **Helper tooltip on a key button** — find a button/heading that's confusing,
   add `data-help="..."` to make it discoverable. Use the `HELP.tip` pattern.
5. **Analytics explainer** — improve the GA4 / Meta / SEO explainer with
   brand-specific example numbers (placeholder until verified).
6. **Brand directory slot** — fill a missing slot for one of the 3 brands
   (e.g. archetypes.json for Stick has 3 archetypes; could add 1-2 more).
7. **Cross-page wiring** — make the Brand switcher propagate to all surfaces,
   or make the "Do this right now" card smarter.

Pick **ONE** thing per tick. Don't try to do everything. Ship one thing well.

### Step 2 — Implement it

- Make the smallest possible change that works.
- If it's a UI change, edit `campaign-os/campaign-os.html`.
- If it's a backend change, edit `campaign-os/app.py`.
- If it's data, edit `data/brand-directory/<brand>/...`.
- Run a quick syntax check before committing: `node -e "const fs=require('fs');const h=fs.readFileSync('campaign-os/campaign-os.html','utf8');const m=h.match(/<script>([\\s\\S]*?)<\\/script>/);new Function(m[1]);console.log('JS OK')"`
- After committing, **push to GitHub** so Railway auto-deploys:
  `git push origin feat/asset-state-engine`
- Wait ~90s for Railway rebuild, then verify the live URL.

### Step 3 — Walkthrough (verify it's not "pig in fancy clothing")

Run a Playwright walkthrough on the live URL. Capture screenshots of the
changed surface. Compare before/after.

**MUST**: zero JS console errors, the new feature is visible, and a non-technical
person could use it.

```python
# Use the existing venv
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
        # ... navigate / click buttons / verify data
        await page.screenshot(path='/tmp/co-nightshift/walkthrough_<TIMESTAMP>.png', full_page=True)
        print('ERRORS:', errs)
        await b.close()
asyncio.run(walk())
"
```

### Step 4 — Honest report

Write to `/tmp/co-nightshift/last-report.md` AND append to `/tmp/co-nightshift/report-log.md`:

```markdown
## Nightshift Report — <ISO timestamp>

### ✅ What was done
- <one concrete shipped thing>

### 📸 Screenshots
- /tmp/co-nightshift/walkthrough_<TIMESTAMP>.png — shows <what>

### ❓ What was rejected and why
- <idea you considered but killed because...>

### 🎯 Next pick (for the NEXT tick)
- <specific next thing>

### 🧠 What I learned / can improve
- <observations from the walkthrough or system>

### 🚨 Blockers / asks for Christelle
- <if anything needs human input, flag here>
```

Then print the report to stdout — the cron delivery will surface it to Discord.

### Step 5 — Confirm deployment

After push + Railway rebuild, verify the live URL is serving the new code:

```bash
curl -s --max-time 30 https://swing-shack-dashboard-production.up.railway.app/api/health
curl -s --max-time 30 https://swing-shack-dashboard-production.up.railway.app/api/brand-directory | python3 -m json.tool | head -20
```

### Step 6 — Quiet

Do NOT loop "still working", "standing by", or similar. The cron delivery is
your single ping per tick. If you have nothing to report, write
`NO_REPORT_NEEDED` to stdout and exit.

## What NOT to do

- Don't try to wire up Google Drive (waiting on credentials).
- Don't publish or schedule anything (standing rule).
- Don't touch `main` branch (only `feat/asset-state-engine`).
- Don't generate fake TrackMan numbers.
- Don't load test the API — the Railway deploy itself is the test.
- Don't run the full test suite every tick (slow); only when you've changed tests.

## Stop conditions

If you hit a hard blocker (GitHub auth broken, Railway down, branch protection
rejecting push), write the blocker to the report and exit. The next tick will
retry or Christelle will see the report on her phone.

## Reference: file layout

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
│   └── ...                         # other data files
├── Dockerfile
├── fly.toml
└── README.md
```

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
