# Operator: approve a plan, put it on the calendar, retitle a step

Someone says: "approve the Black Friday plan", "put the plan on the calendar",
"retitle the Swing Shack plan with Herman's offers", "take it off the calendar".

Campaign OS is built for agents. You do these with `campaign-os/scripts/plan_action.py`
(the repo's `.claude/settings.json` allows it, so the auto-mode classifier does not
stop it). The decision stays the person's: **show first, ask, then act**.

## The loop

1. Find the plan: `python3 campaign-os/scripts/plan_action.py list --brand <brand>`
2. Run the change **without** `--yes`. It prints the plan (every step, date, title) and
   `WOULD ...`. Nothing changes.
3. Paste that to the person and ask one plain question, e.g.
   "Approve the Stick Black Friday plan and put its 16 steps on the calendar? (yes/no)".
4. Only after a clear **yes in chat** for that exact action: run it again with `--yes`.
5. Read back with `show` and tell the person what changed.

A yes covers the action you asked about, nothing more. A new action needs a new yes.

## Commands

```bash
plan_action.py show    --brand stick --plan pln-...
plan_action.py approve --brand stick --plan pln-... --yes
plan_action.py place   --brand stick --plan pln-... --as Christelle --yes
plan_action.py unplace --brand stick --plan pln-... --yes
plan_action.py reopen  --brand stick --plan pln-... --yes
plan_action.py edit    --brand stick --plan pln-... --item itm-... --title "..." --yes
```

On Windows use `python campaign-os\scripts\plan_action.py ...`. Needs `COS_JOB_TOKEN`
(never print it).

## What each does

| Action | Effect | Undo |
|---|---|---|
| approve | Records the yes. Nothing on the calendar yet | `reopen` (only while not placed) |
| place | Puts the steps on the Main Calendar. **Publishes nothing** | `unplace` |
| unplace | Takes the steps off the calendar | `place` again |
| reopen | Approved → editable again (must be unplaced first) | `approve` |
| edit | Changes one step's title | `edit` back |

Retitle a placed plan: `unplace` → `reopen` → `edit` each step → `approve` → `place`.
Show the person the full list of new titles before the first `--yes`.

## Never

- Run `--yes` before the person has said yes to that action.
- Approve a **post** (Approve drafts) on someone's behalf: approving a post releases it.
  Lodge posts with `lodge_post.py --no-approve` (`operator-post.md`).
- Work around a refusal by clicking in the browser pane instead.
