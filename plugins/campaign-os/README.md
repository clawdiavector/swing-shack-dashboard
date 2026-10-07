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

### Skills

| Skill | Load when |
|---|---|
| `campaign-os-map` | **Before building anything.** What already exists — lib modules, the composer, brand templates, Meta/Krea wrappers, and which specs are known wrong. |
| `campaign-os` | Ops hub — jobs, prod health, the ops API, host routing. Opens per-task modules. |
| `campaign-os-template` | Turning a batch of real brand posts into a pixel-accurate compose template. |
| `krea-lab` | Any Krea/Ideogram/Recraft/Flux work — look up model ids, schemas and resolutions *before* generating. |
| `brand-voice-truth` | **Before writing any caption or headline.** What the feed actually says, measured over all 261 Stick posts — the bibles drift and prompts read the bibles. |
| `schedule-from-anywhere` | Putting a finished post (an image made in Claude, or a template render) on the live calendar, This week and the Shelf, ready for Release now, from any machine with a bearer token alone. One command: `lodge_post.py`. |

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
