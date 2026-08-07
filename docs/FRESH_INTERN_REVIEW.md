# Fresh-Intern UX Review — Campaign OS (gen-Z brutal)

> Walked through every tab with zero context. The same notes a new intern
> would scribble on day 1, ranked by effort to fix × impact for Christelle.

## TL;DR — ship these 5 first

| # | Rec | Effort | Impact | Why |
|---|---|---|---|---|
| 1 | **Rename "Meme Lord"** to "Memes" + add a plain-English explainer | 30 min | High | Intern doesn't know if it's offensive, weird, or jargon. |
| 2 | **Rename "+ More tools"** to "All 20 tools" + show count | 30 min | High | "More" is the worst word in software. Tells you nothing. |
| 3 | **Add a global "what is this?"** hover on EVERY nav item, not just selected ones | 2 hrs | High | Right now only some have `data-help` and most don't surface it. |
| 4 | **First-run welcome modal** — "Here's the 5 things you need to know" | 3 hrs | Very High | First-time visit is the worst experience. No onboarding. |
| 5 | **Consolidate the 5 nav sections** (Today / Review / Library / GMB / Create / Brand / quick-links / + More) into a single smart menu | 1 day | Very High | 29 nav items is overwhelming. New intern opens 3 tabs, doesn't know which is which. |

---

## What's CONFUSING (new eyes, no context)

### 🔥 High-impact confusion

1. **No onboarding.** I open the app and see Today. Below that: 29 nav items. Above the fold is text-dense enough that I close the tab. **Fix:** First-run welcome card with 3 things: "Today = what to do now", "Review = approve drafts", "Create = generate content". 2 hours of work.

2. **"Meme Lord" sounds like a meme.** New intern doesn't know if it's slang, a feature, or branding. **Fix:** rename to "Memes" or "Meme Studio". If you love the name, add a one-liner: "Meme Lord — your meme generator" under the title.

3. **"+ More tools" tells me nothing.** 18 tools hide behind it. **Fix:** "All 20 tools" or "Show all tools (20)".

4. **There are 2 "Today" tabs** — the nav says "Today" but also "⚡ Today" right-rail. Both say different things. **Fix:** rename right-rail to "Right now" or "Latest signals".

5. **"Insights" and "Performance" are nearly the same tab.** Both show GA4 + IG metrics. Same data, different framing. **Fix:** merge or rename Performance to "Insights · Performance detail" so it's a sub-page.

6. **"Brand Directory" lives under Brand tab but is buried.** I had to click Brand → look for "directory" → find the 9-slot form. **Fix:** promote to its own nav item: "🎯 Brand Directory".

7. **Learning tab H2 just says "Learning".** What is learning? Who is learning? **Fix:** "Learning — patterns from the last 90 days" (already shipped).

8. **"GMB" is jargon for non-marketers.** Says "Google Business" in the help text but the nav says "GMB". **Fix:** change nav to "Google Business" (the help text already explains it).

### ⚠️ Medium-impact confusion

9. **Calendar needs a "today" button.** When I open it, I'm looking at some random date. New button: "📍 Today" jumps to today.

10. **Publish tab has 4 quadrants (Drafts / Scheduled / Published / Failed).** Great info, but intern doesn't know the flow. **Fix:** add a one-line arrow at the top: "Drafts → set date → Scheduled → auto-publishes → Published (or Failed)".

11. **"Quick links" sidebar group.** Sub-nav under primary items. New intern doesn't know this is a sub-group. **Fix:** visual separation: lighter background or indent indicator.

12. **Meme Lab = external app, but it looks like a sub-tab.** Same for Visual Library and Image Lab. **Fix:** add a small ↗ icon to make it clear these open in the same window to a different page.

13. **Trend Catcher says v2 but never explains what v1 was.** **Fix:** drop "v2" or change to "live signals" so intern doesn't ask "what's v1?"

14. **The "🔬 Why this worked/failed" explainer was broken before this PR.** It existed but the button did nothing because the data wasn't loaded. **Fix:** verified working in current deploy (was a separate issue).

15. **Hooks, Headlines, CTAs, Captions all look the same** — text field + generate button. **Fix:** add a one-liner to each nav item so intern knows: "Hooks — opening lines ranked by what wins".

### 😐 Low-impact (cosmetic)

16. **Emoji-as-icon everywhere.** Tastes vary. Some interns love it, some find it unprofessional. **Fix:** optional: Settings → "minimal mode" that swaps emoji for text.

17. **Right rail ticker is noisy.** "⚡ Today" ticker has 30+ cards. **Fix:** collapse after 5, show "see all" link.

18. **Empty states are honest but verbose.** When there's no data, the cards say "Connect Meta + GA4 to see what is working". Helpful but takes 5 lines. **Fix:** 2 lines + a button.

---

## What's MISSING (new intern asking)

1. **No "first 24 hours" guide.** Where do I start today? **Fix:** welcome modal OR a sticky card on Today that says "Day 1 with Campaign OS? Start here →"

2. **No way to know which tab is "important" vs "advanced".** All tabs look the same. **Fix:** subtle labels: "Daily" / "Weekly" / "Advanced" next to each tab.

3. **No keyboard shortcuts.** Power users love them. **Fix:** `?` opens shortcut overlay. `g+t` = go to Today, `g+r` = go to Review, etc.

4. **No recent activity feed.** "What changed since I last opened this?" **Fix:** add a "Recent activity" card to Today (shows what got approved, scheduled, published in the last 24h).

5. **No way to mark something as "done".** When I approve a post, where's the "✓" so I know I did it? **Fix:** subtle "last reviewed at" timestamp on each card.

6. **No undo on most actions.** I approved a thing by accident. Where's undo? **Fix:** toast that says "✓ Approved · Undo" with a 5-second window.

7. **No "saved views".** I have my own way of reading insights. **Fix:** let me pin a filter (e.g. "only Swing Shack") as the default.

8. **No "compare two posts" view.** I want to see post A and post B side by side. **Fix:** checkbox on each card → "compare" button appears.

9. **No "what should I do this week" summary.** Today has "do this right now", but what about the whole week? **Fix:** add a "This week" tab or expand Today rail.

10. **No SLA timer on review queue.** "This draft has been waiting 3 days" would help me prioritize. **Fix:** show age in red after 24h.

---

## What's GREAT (don't touch)

- **Image Lab + Socials + Meme thumbnails** (just shipped) — feels modern, image-first, matches how marketing actually works
- **The voice bible + pillars** concept — gives the system a consistent identity
- **Auto-compose image gen** — pulls all 4 layers (brand + product + reference DNA + learned). This is genuinely impressive.
- **Per-asset IG carousel in Review modal** — answers "have we said this before" before approving
- **Inline caption editing in Review modal** — small but huge UX win
- **Color-coded signals (green/yellow/red)** — instant comprehension
- **Trends freshness banner** (just shipped) — finally tells you when data is stale
- **🔍 Explain** explainer pattern on most cards — interns who hover learn fast

---

## Effort × Impact ranking

```
QUICK WINS (ship today, < 1 day each):
  ▸ Rename "+ More tools" to "All 20 tools"              30 min, high
  ▸ Add count badge to "All tools" toggle                 15 min, high
  ▸ Rename "GMB" → "Google Business" in nav               15 min, medium
  ▸ Rename "Meme Lord" → "Memes" or add explainer         30 min, medium
  ▸ Add "📍 Today" button to Calendar                    20 min, medium
  ▸ Add Publish flow arrow (Drafts → Scheduled → Live)    30 min, medium
  ▸ Surface data-help tooltips on every nav item          2 hrs,  high

MEDIUM BUILDS (1-3 days each):
  ▸ First-run welcome modal                               3 hrs,  very high
  ▸ Add "Daily / Weekly / Advanced" labels to nav          4 hrs,  high
  ▸ Add SLA timer on review queue                         4 hrs,  medium
  ▸ Recent-activity feed on Today                         6 hrs,  high
  ▸ Undo toast for approve/reject                         4 hrs,  medium

BIG BUILDS (1+ week each):
  ▸ Consolidate nav into smart single menu                1 wk,   very high
  ▸ Keyboard shortcuts + overlay                          1 wk,   medium
  ▸ Compare two posts side-by-side                        1 wk,   medium
  ▸ Saved views / personalisation                        1 wk,   medium
```

---

## Top 3 things I'd ship tomorrow

1. **First-run welcome modal** — biggest impact-per-hour. New intern gets it the moment they need it most (second 0).
2. **Surface data-help tooltips on every nav item** — most nav items already have `data-help` but the hover pattern only works inside cards. Wire it everywhere.
3. **Rename "+ More tools" + add "Daily / Weekly / Advanced" labels** — costs an hour, makes the 29-item nav feel less overwhelming.