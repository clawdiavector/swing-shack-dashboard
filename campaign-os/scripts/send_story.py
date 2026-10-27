#!/usr/bin/env python3
"""Send finished 9:16 images to Postiz as Instagram stories (draft unless --schedule).

    python campaign-os/scripts/send_story.py --brand swing-shack \\
        --image ss-1.jpg --at "2026-10-28 17:30" [--schedule] [--dry-run]

--at is South African time. Repeat --image/--at as pairs, in the same order. Needs the brand's own
Postiz key in the environment (POSTIZ_API_KEY_<BRAND>); on this repo's Railway project run it with
`railway run python ...`. Facebook stories are not supported by Postiz, so only Instagram is used.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import postiz_client as pz  # noqa: E402

SAST = ZoneInfo("Africa/Johannesburg")


def to_utc_iso(local: str) -> str:
    when = datetime.strptime(local, "%Y-%m-%d %H:%M").replace(tzinfo=SAST)
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def instagram_channel(brand: str) -> dict:
    data, err = pz.list_integrations(brand_id=brand)
    if err:
        raise SystemExit("Postiz error %s: %s" % err)
    items = data if isinstance(data, list) else ((data or {}).get("integrations") or (data or {}).get("identities") or [])
    for item in items:
        if not isinstance(item, dict) or item.get("disabled"):
            continue
        provider = next((str(item[k]).lower() for k in ("identifier", "providerIdentifier", "provider", "type")
                         if isinstance(item.get(k), str) and item.get(k)), "")
        if provider.startswith("instagram"):
            return {"id": item["id"], "provider": provider, "name": item.get("name")}
    raise SystemExit("no Instagram channel is connected in Postiz for %s" % brand)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True, choices=["swing-shack", "stick", "bag-drop"])
    ap.add_argument("--image", action="append", required=True)
    ap.add_argument("--at", action="append", required=True, help='"YYYY-MM-DD HH:MM" South African time')
    ap.add_argument("--schedule", action="store_true", help="schedule it; the default saves a draft that publishes nothing")
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent and stop")
    args = ap.parse_args(argv)
    if len(args.image) != len(args.at):
        ap.error("give one --at for each --image")
    for path in args.image:
        if not Path(path).is_file():
            ap.error("not a file: %s" % path)
    when = [to_utc_iso(a) for a in args.at]
    if args.dry_run:
        for path, w in zip(args.image, when):
            print("would send %s to %s Instagram as a %s story at %s" % (
                path, args.brand, "scheduled" if args.schedule else "draft", w))
        return 0
    if not pz.has_brand_key(args.brand):
        raise SystemExit("no Postiz key for %s (POSTIZ_API_KEY_%s)" % (args.brand, args.brand.upper().replace("-", "_")))
    channel = instagram_channel(args.brand)
    for path, w in zip(args.image, when):
        data, err = pz.create_story(channel["id"], channel["provider"], path, brand_id=args.brand,
                                    publish_date=w, draft=not args.schedule)
        if err:
            print("FAILED %s: %s %s" % (path, err[0], err[1]))
            return 1
        print("ok %s -> %s at %s (%s)" % (Path(path).name, channel["name"], w, "scheduled" if args.schedule else "draft"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
