#!/usr/bin/env python3
"""Put one finished post on the live Campaign OS shelf, from any machine.

Standard library only, so it runs on Windows, macOS or Linux with nothing
installed. Needs COS_JOB_TOKEN in the environment.

    python campaign-os/scripts/lodge_post.py \\
        --brand swing-shack --slug spoon-wrong-clubs --date 2026-10-09 \\
        --image spoon-wrong-clubs.jpg --caption-file caption.txt --by christelle

    # compose from a measured template instead of sending a picture
    python campaign-os/scripts/lodge_post.py \\
        --brand swing-shack --slug spoon-template --date 2026-10-09 \\
        --archetype ss-fitting-headline \\
        --field "caption_hook=YOU WOULDN'T DIG WITH A SPOON." \\
        --field "service_lockup=WHY PLAY THE WRONG CLUBS?" \\
        --caption "You wouldn't dig with a spoon..."

The post lands on the shelf as Scheduled. A person clicks Release now in
Campaign OS (Shelf page) to send it. Lodging the same --slug again replaces
the picture or caption in the same calendar slot.

Exit codes: 0 lodged, 1 refused by the server, 2 bad arguments or no token.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://swing-shack-dashboard-production.up.railway.app"


def build_body(a: argparse.Namespace) -> dict:
    if a.caption_file:
        caption = Path(a.caption_file).read_text(encoding="utf-8")
    else:
        caption = a.caption or ""
    body: dict = {
        "brand": a.brand,
        "slug": a.slug,
        "date": a.date,
        "caption": caption,
        "created_by": a.by,
        "approve": not a.no_approve,
    }
    if a.image:
        body["image_base64"] = base64.b64encode(Path(a.image).read_bytes()).decode()
    if a.archetype:
        body["archetype"] = a.archetype
    if a.field:
        fields = {}
        for kv in a.field:
            if "=" not in kv:
                raise SystemExit(f"--field needs KEY=VALUE, got {kv!r}")
            k, v = kv.split("=", 1)
            fields[k.strip()] = v
        body["fields"] = fields
    if a.channels:
        body["channels"] = [c.strip() for c in a.channels.split(",") if c.strip()]
    if a.title:
        body["title"] = a.title
    return body


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True, choices=("swing-shack", "stick", "bag-drop"))
    ap.add_argument("--slug", required=True,
                    help="lowercase-hyphenated id; the same slug again replaces the post")
    ap.add_argument("--date", required=True, help="go-live day, YYYY-MM-DD")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="a finished picture (JPEG, PNG or WebP), placed as-is")
    src.add_argument("--archetype", help="compose from a measured template instead")
    cap = ap.add_mutually_exclusive_group(required=True)
    cap.add_argument("--caption")
    cap.add_argument("--caption-file", help="UTF-8 text file holding the caption")
    ap.add_argument("--field", action="append", default=[], metavar="KEY=VALUE",
                    help="template text zone (with --archetype)")
    ap.add_argument("--channels", help="comma-separated; default is the brand's own (Instagram + Facebook)")
    ap.add_argument("--title", help="calendar title; default is the caption's first line")
    ap.add_argument("--by", default=os.environ.get("USER") or os.environ.get("USERNAME") or "operator",
                    help="your name, recorded on the post")
    ap.add_argument("--no-approve", action="store_true",
                    help="stop in Review instead of putting it on the shelf")
    ap.add_argument("--base", default=os.environ.get("COS_BASE_URL", DEFAULT_BASE))
    a = ap.parse_args()

    token = os.environ.get("COS_JOB_TOKEN", "").strip()
    if not token:
        print("COS_JOB_TOKEN is not set. Ask Kyle for it, then set it in your shell.",
              file=sys.stderr)
        return 2
    if a.image and not Path(a.image).is_file():
        print(f"image not found: {a.image}", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        a.base.rstrip("/") + "/api/posts/lodge",
        data=json.dumps(build_body(a)).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 # The calendar only books an approved slot for a named person.
                 "X-Actor-Display-Name": a.by},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            doc = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            doc = json.loads(e.read())
        except ValueError:
            doc = {"error": f"HTTP {e.code}"}
        print(f"refused ({e.code}): {doc.get('error')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"could not reach {a.base}: {e.reason}", file=sys.stderr)
        return 1

    links = doc.get("links") or {}
    print(f"lodged   {doc.get('event_key')}  for {doc.get('go_live_date')}")
    print(f"state    {doc.get('state')} — {doc.get('next_action')}")
    for ch, url in (doc.get("images") or {}).items():
        print(f"image    {ch:<10} {url}")
    for note in doc.get("notes") or []:
        print(f"note     {note}")
    if doc.get("state") == "scheduled":
        print(f"release  {links.get('shelf')}  (click Release now)")
    else:
        print(f"review   {links.get('review')}")
    print(f"week     {links.get('week')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
