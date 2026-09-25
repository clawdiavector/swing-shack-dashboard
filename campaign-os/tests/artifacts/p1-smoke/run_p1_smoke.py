#!/usr/bin/env python3
"""Real smoke: OpenRouter gemini + reference, Krea flux ultra (no reference)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent
HANDOFF = OUT / "handoff.json"


def _find_reference_png() -> Path | None:
    images = REPO / "data" / "brand-directory" / "swing-shack" / "images"
    if not images.is_dir():
        return None
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        hits = sorted(images.glob(ext))
        if hits:
            return hits[0]
    return None


def main() -> int:
    from _lib import image_gen_router as router

    or_ok = router.openrouter_credentials_present()
    krea_ok = router._krea_credentials_present()
    report: dict = {"openrouter_configured": or_ok, "krea_configured": krea_ok, "calls": []}

    if not or_ok and not krea_ok:
        report["skipped"] = "no OPENROUTER_API_KEY or Krea credentials locally"
        HANDOFF.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    total = 0.0

    if or_ok:
        ref_path = _find_reference_png()
        if not ref_path:
            report["openrouter_skip"] = "no reference PNG under data/brand-directory/swing-shack/images/"
        else:
            ref_bytes = ref_path.read_bytes()
            result = router.generate_image(
                "Studio golf coaching bay, warm light, no text",
                provider="openrouter",
                model="google/gemini-2.5-flash-image",
                reference_bytes=[ref_bytes],
                size="1024x1024",
                save=False,
                max_cost_usd=0.15,
            )
            out_path = OUT / "openrouter-gemini-reference.png"
            out_path.write_bytes(result.bytes)
            total += float(result.cost_usd or 0)
            report["calls"].append(
                {
                    "path": str(out_path),
                    "provider": result.provider,
                    "model": result.model,
                    "cost_usd": result.cost_usd,
                    "source": result.cost_source,
                }
            )

    if krea_ok:
        result = router.generate_image(
            "Product hero golf iron on matte background, photoreal, no text",
            provider="krea",
            model="bfl/flux-1.1-pro-ultra",
            size="1024x1024",
            save=False,
            max_cost_usd=0.15,
        )
        if result.provider_job_id and not result.bytes:
            report["krea_note"] = f"async job {result.provider_job_id}; poll separately for PNG"
        elif result.bytes:
            out_path = OUT / "krea-flux-ultra.png"
            out_path.write_bytes(result.bytes)
            total += float(result.cost_usd or 0)
            report["calls"].append(
                {
                    "path": str(out_path),
                    "provider": result.provider,
                    "model": result.model,
                    "cost_usd": result.cost_usd,
                    "source": result.cost_source,
                }
            )

    report["total_cost_usd"] = round(total, 4)
    report["under_budget_0_20"] = total < 0.20
    HANDOFF.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if total < 0.20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
