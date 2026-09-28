#!/usr/bin/env python3
"""Render ss-ladies-clinic goldens + reference comparison sheet."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN))

from PIL import Image  # noqa: E402

from _lib.archetype_compose import compose_post_for_channels  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402

PACK = ROOT / "data/brand-directory/swing-shack/templates/ladies-clinic"
CASES_PATH = PACK / "cases.json"


def main() -> int:
    arch = archetype_by_id("swing-shack", "ss-ladies-clinic")
    if not arch:
        print("ss-ladies-clinic archetype missing", file=sys.stderr)
        return 1
    cases = json.loads(CASES_PATH.read_text())
    golden = PACK / "golden"
    golden.mkdir(parents=True, exist_ok=True)
    tw, th = 360, 400
    sheet = Image.new("RGB", (len(cases) * tw, 2 * th), "white")
    for i, case in enumerate(cases):
        fields = {k: str(v) for k, v in case.items()}
        page = fields.get("render_page", "page1")
        out = compose_post_for_channels(
            brand_id="swing-shack",
            archetype=arch,
            channels=["instagram"],
            fields=fields,
            photo_bytes=None,
        )
        png = out["instagram"] if page == "page1" else out.get("instagram__page2") or out["instagram"]
        if page == "page1":
            (golden / "render-page1.png").write_bytes(png)
        else:
            (golden / "render-page2.png").write_bytes(png)
        ref = Image.open(PACK / f"references/ref-0{i + 1}.jpg").convert("RGB")
        ours = Image.open(io.BytesIO(png)).convert("RGB")
        for row, im in enumerate((ref, ours)):
            im.thumbnail((tw - 6, th - 6))
            sheet.paste(im, (i * tw + 3, row * th + 3))
    sheet.save(golden / "compare-refs.jpg", quality=85)
    print(f"wrote goldens + compare sheet under {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
