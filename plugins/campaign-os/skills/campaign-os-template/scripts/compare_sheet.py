#!/usr/bin/env python3
"""Render an archetype with each reference's copy and build a refs-vs-renders sheet.

Run from a swing-shack-dashboard worktree. cases.json is a list matching the
sorted reference files: [{"caption_hook": "...", "accent": "ss_green", "cta": "..."}, ...]
Output filename carries a timestamp — image viewers cache same-name files.

  python3 compare_sheet.py --repo <worktree> --brand swing-shack --archetype ss-did-you-know \
      --refs <pack>/references --cases cases.json --out /tmp/cmp
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--archetype", required=True)
    ap.add_argument("--refs", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", default="/tmp/template-compare")
    ap.add_argument("--channels", default="instagram,instagram_story")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(args.repo) / "campaign-os"))
    from _lib.archetype_compose import compose_post_for_channels  # noqa: PLC0415 — repo path set at runtime
    from _lib.archetypes import archetype_by_id  # noqa: PLC0415

    arch = archetype_by_id(args.brand, args.archetype)
    if not arch:
        raise SystemExit(f"archetype {args.archetype} not found for {args.brand} (edited archetypes.json in this worktree?)")
    refs = sorted(p for p in Path(args.refs).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    cases = json.loads(Path(args.cases).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    tw, th = 360, 450
    sheet = Image.new("RGB", (max(1, len(cases)) * tw, 2 * th + 20), "white")
    draw = ImageDraw.Draw(sheet)
    channels = args.channels.split(",")
    for i, fields in enumerate(cases):
        rendered = compose_post_for_channels(
            brand_id=args.brand, archetype=arch, channels=channels, fields=fields, photo_bytes=None
        )
        for ch, png in rendered.items():
            (out / f"{i + 1:02d}-{ch}-{stamp}.png").write_bytes(png)
        ours = Image.open(io.BytesIO(rendered[channels[0]])).convert("RGB")
        if i < len(refs):
            ref = Image.open(refs[i]).convert("RGB")
            ref.thumbnail((tw - 6, th - 6))
            sheet.paste(ref, (i * tw + 3, 3))
        ours.thumbnail((tw - 6, th - 6))
        sheet.paste(ours, (i * tw + 3, th + 17))
    draw.text((4, th + 2), "top: reference   bottom: render", fill="black")
    path = out / f"compare-{args.archetype}-{stamp}.jpg"
    sheet.save(path, quality=85)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
