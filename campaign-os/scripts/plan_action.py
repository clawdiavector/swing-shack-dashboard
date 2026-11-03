#!/usr/bin/env python3
"""Look at a campaign plan, and approve it, put it on the calendar or take it off, from any machine.

Standard library only. Needs COS_JOB_TOKEN in the environment (never printed).

    python campaign-os/scripts/plan_action.py list --brand stick
    python campaign-os/scripts/plan_action.py show --brand stick --plan pln-e39cbd72d5

    # changes: without --yes these only print what would change, then stop
    python campaign-os/scripts/plan_action.py approve --brand stick --plan pln-... [--yes]
    python campaign-os/scripts/plan_action.py place   --brand stick --plan pln-... --as Christelle [--yes]
    python campaign-os/scripts/plan_action.py unplace --brand stick --plan pln-... [--yes]
    python campaign-os/scripts/plan_action.py reopen  --brand stick --plan pln-... [--yes]
    python campaign-os/scripts/plan_action.py edit    --brand stick --plan pln-... --item itm-... --title "New title" [--yes]

Agents: run the command without --yes, show the person what it prints, and run it again
with --yes only after the person says yes in chat. Approving and placing are the person's
decision; this script is how an agent carries it out. Place puts steps on the Main Calendar
but publishes nothing; unplace undoes it.

Exit codes: 0 done (or dry run shown), 1 refused by the server, 2 bad arguments or no token.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://swing-shack-dashboard-production.up.railway.app"
BRANDS = ("swing-shack", "stick", "bag-drop")
CHANGES = ("approve", "place", "unplace", "reopen", "edit")


def call(base: str, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    token = os.environ.get("COS_JOB_TOKEN", "")
    if not token:
        raise SystemExit("COS_JOB_TOKEN is not set")
    req = urllib.request.Request(base.rstrip("/") + path, method=method)
    req.add_header("Authorization", "Bearer " + token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"ok": False, "error": e.reason}


def summary(plan: dict) -> str:
    lines = [
        f"plan     {plan.get('id')}  ({plan.get('brand_id') or ''})",
        f"title    {plan.get('title') or plan.get('name') or ''}",
        f"status   {plan.get('status')}" + ("  placed " + str(plan.get('placed_at')) if plan.get('placed_at') else "  not on the calendar"),
    ]
    items = [i for i in (plan.get("items") or []) if i.get("status") != "removed"]
    lines.append(f"steps    {len(items)}")
    for i in items:
        lines.append(f"  {i.get('due') or '----------'}  {i.get('kind') or '':<8} {i.get('title') or ''}  [{i.get('id')}]")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("list", "show") + CHANGES)
    ap.add_argument("--brand", required=True, choices=BRANDS)
    ap.add_argument("--plan")
    ap.add_argument("--item", help="edit: the step id (from show)")
    ap.add_argument("--title", help="edit: the step's new title")
    ap.add_argument("--as", dest="actor", help="your name; place needs it (the calendar books named slots only)")
    ap.add_argument("--yes", action="store_true", help="make the change; without it, only show what would change")
    ap.add_argument("--base", default=os.environ.get("COS_BASE_URL", DEFAULT_BASE))
    a = ap.parse_args()

    if a.action == "list":
        code, r = call(a.base, "GET", f"/api/plan/v1/{a.brand}/list")
        if code != 200:
            print(f"refused ({code}): {r.get('error')}")
            return 1
        for p in r.get("plans") or []:
            print(f"{p.get('id')}  {p.get('status'):<10} {'placed' if p.get('placed_at') else '      '}  {p.get('title') or p.get('name') or ''}")
        return 0

    if not a.plan:
        ap.error("--plan is required")
    code, r = call(a.base, "GET", f"/api/plan/v1/{a.brand}/{a.plan}")
    if code != 200:
        print(f"refused ({code}): {r.get('error')}")
        return 1
    plan = r["plan"]
    print(summary(plan))
    if a.action == "show":
        return 0

    if a.action == "edit" and not (a.item and a.title):
        ap.error("edit needs --item and --title")
    if a.action == "place" and not a.actor:
        ap.error("place needs --as <your name>")
    what = {
        "approve": "record the yes on this plan (nothing goes on the calendar yet)",
        "place": "put these steps on the Main Calendar (nothing is published)",
        "unplace": "take this plan's steps off the Main Calendar",
        "reopen": "reopen this approved plan for editing",
        "edit": f"retitle step {a.item} to: {a.title}",
    }[a.action]
    if not a.yes:
        print(f"\nWOULD {what}.\nNothing changed. Ask the person; run again with --yes once they say yes.")
        return 0

    actor = a.actor or os.environ.get("USER") or "agent"
    path = f"/api/plan/v1/{a.brand}/{a.plan}"
    if a.action == "edit":
        code, r = call(a.base, "PATCH", f"{path}/item/{a.item}", {"title": a.title, "actor": actor})
    elif a.action == "place":
        code, r = call(a.base, "POST", f"{path}/place", {}, {"X-Actor-Display-Name": actor})
    else:
        code, r = call(a.base, "POST", f"{path}/{a.action}", {"actor": actor})
    if code != 200 or not r.get("ok"):
        print(f"\nrefused ({code}): {r.get('error')}")
        return 1
    print(f"\nDONE: {what}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
