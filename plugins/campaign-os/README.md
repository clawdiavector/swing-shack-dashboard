# campaign-os (Claude Code plugin)

Marketing operations for **Swing Shack**, **Stick** and **Bag Drop**, packaged so a
teammate goes from `git clone` to working in two commands.

Before this plugin existed the capability was scattered across four places, two of
which were not in git at all (`~/.agents/skills/` on one Linux box, unbacked). That
is why this exists: **the plugin is now the canonical home** for these skills.

## What you get

### Commands

| Command | Does |
|---|---|
| `/audit-social <brand>` | Pulls the brand's whole Instagram catalogue with insights and full-res images. The output is the source of **real** voice — prefer it over the copy bible when they disagree. |
| `/render-post` | Renders a post from a measured template. Deterministic, ~200ms, correct text, free. **Run `--list` first, every time.** |
| `/schedule-post` | Turns rendered images into real posts — caption, date, state, Review queue. A PNG on disk appears nowhere in the UI. |
| `/verify-specs` | Probes the specs this repo silently drifts on and reports what is actually true. Free — no credits, no posts. |
| `/campaign-os:mail <who> <what>` · `mail setup` | Email a teammate from your own agent inbox: PR to review, new skill/template/framework, plugin update. Contact list in `skills/campaign-os-mail/contacts.json`. |
| `/campaign-os:wiki-read` · `wiki-write` · `wiki-test` | Read from, file to, and self-test the shared Campaign OS wiki (see "The wiki" below). |

### Skills

| Skill | Load when |
|---|---|
| `campaign-os-map` | **Before building anything.** What already exists — lib modules, the composer, brand templates, Meta/Krea wrappers, and which specs are known wrong. |
| `campaign-os` | Ops hub — jobs, prod health, the ops API, host routing. Opens per-task modules. |
| `campaign-os-campaign` | **Set up / create a campaign, TEST n, Suggest Date, Brief.** Run `suggest_campaign.py` only. Not a lodge. |
| `campaign-os-template` | Turning a batch of real brand posts into a pixel-accurate compose template. |
| `krea-lab` | Any Krea/Ideogram/Recraft/Flux work — look up model ids, schemas and resolutions *before* generating. |
| `visual-design` | **Before designing or reviewing any post, story, carousel or ad still.** Christelle's art-direction rules: one idea, one move, type as design, eight recipes rotated, three real directions, hard fails, and the 40/50 publish score. Scores with the poster and post formulas in `formulas.md`. |
| `reel-formula` | **Before scripting, editing, reviewing or boosting any reel, story or video ad.** Reel = Native × (Hook + Story + Rhythm + Sound + Brand) × Ask: time shape, safe zones for reels and stories, cut rhythm, lengths by job, the order to read the numbers. |
| `brand-voice-truth` | **Before writing any caption or headline.** What the feed actually says, measured over all 261 Stick posts — the bibles drift and prompts read the bibles. |
| `the-algorithm` | **Before building, adding or automating anything.** Question the requirement → delete → simplify → accelerate → automate. `/the-algorithm` switches on two light hooks for that session only — a one-line reminder per prompt and a one-time challenge on new files in `_lib/`, `scripts/` or the plugin. `/the-algorithm off` mutes them. Or `/the-algorithm <job or script>` to run it on something that already exists. |
| `campaign-os-wiki` | **Before research, and after it.** The shared Campaign OS wiki (private repo `clawdiavector/campaign-os-wiki`): what is already known, and where findings get filed so Kyle's and Christelle's Claude both see them. |
| `campaign-os-mail` | **When you tell or ask a teammate something.** Your own AgentMail inbox + a shared contact list (who is who, when to send). First-time setup in `SETUP.md`; hand `PROMPT-FOR-CHRISTELLE.md` to a teammate's Claude. |
| `campaign-os-carousel` | **A carousel / swipe post.** Christelle's design guide (hero that stops people, one colour story, slides that unfold, simple close), when a carousel beats a single or a video, `carousel_check.py` for the set, and lodging (slide 1 only until wiki task T18 lands). |
| `reality-check` | **Before showing any real-looking image** (photo, generated scene, layered build): real-world scale with `reality_check.py`, then depth, physics, light, shape, stock, people, ends in frame and load. A standing rule, not just for carousels. |
| `cad-designer` | **3D renders, floor plans, blueprints, isometric layouts.** True-scale scenes in metres (a bay, a golfer, the real logo on the screen) from any camera, in blueprint, plan or clay style; the render is a building-plan post or the exact layout Krea paints on. |
| `campaign-os-efforts` | **Monthly marketing efforts pack.** Five things people take part in (leaderboards, challenge nights, countdowns, hunts, weather triggers), art-directed mockups on real photos with `mockup_kit.py`, dated roll-outs and a confirm list, on one review page by the 15th. |
| `schedule-from-anywhere` | Putting a finished post (an image made in Claude, or a template render) on the live calendar, This week and the Shelf, ready for Release now, from any machine with a bearer token alone. One command: `lodge_post.py`. |

## The wiki (research that survives the session)

Hooks ship with the plugin, so installing it is the whole setup: on session start Claude clones and syncs `~/CampaignOSKnowledgeBase`, injects a short brief, suggests wiki pages that match what you type, and once per session reminds itself to file Campaign OS research that nothing recorded. Needs read/write access to `clawdiavector/campaign-os-wiki` (a GitHub invite, then `gh auth login`). Disable with `CAMPAIGNOS_KB_HOOKS=off`. Details: `skills/campaign-os-wiki/SKILL.md`.

## Install / update (teammates)

```bash
claude plugin marketplace add clawdiavector/swing-shack-dashboard   # first time
claude plugin install campaign-os@campaign-os                       # first time
claude plugin marketplace update campaign-os && claude plugin update campaign-os@campaign-os   # to get new versions
```

## The two rules that cost the most when broken

1. **Search before you build.** On 2026-10-05 a full day went into art-directing a
   poster `compose_post_for_channels()` already rendered from an existing template,
   and the "winning prompt" turned out to describe a reference image sitting in the
   template pack. Separately, an hour went into scraping Instagram while
   `_lib/meta_api.py` sat unused.
2. **Deterministic beats generated.** If a layout is known, render it. An image model
   garbles type, drifts off palette, invents logos, and costs credits and a one-shot
   slot per attempt. Reach for Krea only for genuinely new looks or photography that
   does not exist yet — then measure the winner into a template with
   `campaign-os-template` so it graduates down.

## Requires

The **`swing-shack-dashboard` repo as the working directory** — every command shells
into `campaign-os/scripts/`, and the brand data, templates and fonts live in `data/`.
The plugin carries the knowledge; the repo carries the code. Setup for both:
[`docs/ONBOARDING-MARKETING.md`](../../docs/ONBOARDING-MARKETING.md).

Krea's MCP server is defined by the **repo's** root `.mcp.json`, not by this plugin,
so there is exactly one `krea` server however you load this.

## Host note

Some of the `campaign-os` skill's modules describe Kyle's desk specifically — the
Hermes agent fleet, the Mac bridge, the `agent-control` foreman repo, scheduled
launchd jobs. Those are marked inline. Everything in the table above works on any
machine with the repo and the right credentials.
