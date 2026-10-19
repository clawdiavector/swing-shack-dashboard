#!/usr/bin/env python3
"""Load a Suggest Date candidate (Waiting for you). Does not approve, upsert, enqueue or publish.

    python3 campaign-os/scripts/suggest_campaign.py \\
        --brand swing-shack --title "TEST 3" \\
        --start 2026-10-24 --pillar fitting \\
        --why "Push fittings with a humorous angle. Off-the-rack is for groceries."

Needs COS_JOB_TOKEN (presence only). --dry-run prints the card and does not POST.
Exit 0 on a loaded (or dry-run) card, 2 on bad arguments, 1 on API failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

BRANDS = ("swing-shack", "stick", "bag-drop")
BRAND_ALIASES = {
    "ss": "swing-shack",
    "swing shack": "swing-shack",
    "swingshack": "swing-shack",
}
PILLAR_NAME = {
    "fitting": {"swing-shack": "ss-fitting", "stick": "stick-fitting"},
    "coaching": {"swing-shack": "ss-coaching", "stick": "stick-coaching"},
    "retail": {"swing-shack": "ss-retail", "stick": "stick-retail"},
    "membership": {"swing-shack": "ss-membership"},
}
PROD = "https://swing-shack-dashboard-production.up.railway.app"


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    candidates = []
    if len(here.parents) >= 3:
        candidates.append(here.parents[2])
    candidates.append(
        Path.home() / "finder-workspace/repos/work/swing-shack-dashboard-main"
    )
    for root in candidates:
        if (root / "data" / "brand-directory").is_dir():
            return root
    return candidates[-1]


ROOT = _repo_root()


def _brand(raw: str) -> str:
    key = raw.strip().lower().replace("_", "-")
    key = BRAND_ALIASES.get(key, key)
    if key not in BRANDS:
        raise argparse.ArgumentTypeError(
            f"brand must be one of {', '.join(BRANDS)}"
        )
    return key


def _iso(raw: str) -> str:
    try:
        return date.fromisoformat(raw.strip()).isoformat()
    except ValueError as e:
        raise argparse.ArgumentTypeError("dates must be YYYY-MM-DD") from e


def _pillar_id(brand: str, raw: str) -> str:
    text = raw.strip()
    low = text.lower().replace("_", "-")
    if low.startswith(("ss-", "stick-", "bags-")):
        return low
    mapped = (PILLAR_NAME.get(low) or {}).get(brand)
    if mapped:
        return mapped
    cfg = ROOT / "data" / "brand-directory" / brand / "calendar_config.json"
    try:
        pillars = json.loads(cfg.read_text(encoding="utf-8")).get("pillars") or []
    except OSError:
        pillars = []
    for p in pillars:
        pid = str(p.get("pillar_id") or "")
        name = str(p.get("name") or "")
        if low in (pid.lower(), name.lower()):
            return pid
    raise argparse.ArgumentTypeError(
        f"unknown pillar {raw!r} for {brand}"
    )


def _label(brand: str, pillar_id: str) -> str:
    cfg = ROOT / "data" / "brand-directory" / brand / "calendar_config.json"
    try:
        pillars = json.loads(cfg.read_text(encoding="utf-8")).get("pillars") or []
    except OSError:
        pillars = []
    for p in pillars:
        if str(p.get("pillar_id") or "") == pillar_id:
            return str(p.get("name") or pillar_id)
    return pillar_id


def _body(brand: str, title: str, start: str, end: str, pillar: str, why: str) -> dict:
    return {
        "brand_id": brand,
        "type": "campaign",
        "status": "candidate",
        "title": title,
        "start": start,
        "end": end,
        "public_peak": start,
        "source": "OPERATOR_PROVIDED",
        "source_kind": "operator",
        "importance": "ASSESS",
        "notes": "",
        "created_by": "operator",
        "evidence_kind": "OPERATOR_PROVIDED",
        "is_suggested": True,
        "why_it_matters": why,
        "pillars": [pillar],
    }


def _print_card(brand: str, title: str, start: str, end: str, pillar: str, why: str) -> None:
    display = {
        "swing-shack": "Swing Shack",
        "stick": "Stick",
        "bag-drop": "Bag Drop",
    }[brand]
    print(f"  Title:        {title}")
    print("  Type:         Campaign")
    print(f"  Pillar:       {_label(brand, pillar)} ({pillar})")
    print(f"  Start / end:  {start} → {end}")
    print(f"  Brand:        {display}")
    print(f"  Why:          {why or '(leave blank)'}")


def _post(payload: dict) -> tuple[int, dict]:
    token = (os.environ.get("COS_JOB_TOKEN") or "").strip()
    if not token:
        print("COS_JOB_TOKEN is not set", file=sys.stderr)
        return 1, {}
    base = (os.environ.get("CAMPAIGN_OS_URL") or PROD).rstrip("/")
    req = urllib.request.Request(
        f"{base}/api/calendar/candidates",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            return resp.status, raw if isinstance(raw, dict) else {}
    except urllib.error.HTTPError as e:
        try:
            raw = json.loads(e.read().decode("utf-8"))
        except Exception:
            raw = {"ok": False, "error": f"HTTP {e.code}"}
        if not isinstance(raw, dict):
            raw = {"ok": False, "error": f"HTTP {e.code}"}
        return e.code, raw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--brand", required=True, type=_brand)
    p.add_argument("--title", required=True)
    p.add_argument("--start", required=True, type=_iso)
    p.add_argument("--end", default="", type=str)
    p.add_argument("--pillar", required=True)
    p.add_argument("--why", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    end = _iso(args.end) if args.end.strip() else args.start
    if date.fromisoformat(end) < date.fromisoformat(args.start):
        print("end is before start", file=sys.stderr)
        return 2
    try:
        pillar = _pillar_id(args.brand, args.pillar)
    except argparse.ArgumentTypeError as e:
        print(e, file=sys.stderr)
        return 2
    why = args.why.strip()
    title = args.title.strip()
    _print_card(args.brand, title, args.start, end, pillar, why)
    if args.dry_run:
        print()
        print("Dry-run. Did not POST.")
        return 0
    code, data = _post(_body(args.brand, title, args.start, end, pillar, why))
    rec = data.get("record") if isinstance(data.get("record"), dict) else {}
    cid = rec.get("calendar_id") or rec.get("id")
    if code in (200, 201) and data.get("ok"):
        print()
        print(f"Loaded. Waiting for you. calendar_id={cid}")
        print("Add to Main Calendar is still a human click. No Brief, Plan, lodge or publish.")
        return 0
    err = data.get("error") or f"HTTP {code}"
    print()
    if code == 401:
        print(
            "Blocked: prod still session-only for Suggest Date. "
            "Needs dual-auth deploy. Did not lodge.",
            file=sys.stderr,
        )
    else:
        print(f"Blocked: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
