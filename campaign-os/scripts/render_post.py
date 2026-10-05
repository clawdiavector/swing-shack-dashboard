#!/usr/bin/env python3
"""Render a post from a measured template — deterministic, ~200ms, no credits.

If a layout is known, render it. compose_post_for_channels() produces
pixel-identical output with correct text for free; an image model garbles type,
drifts off palette, invents logos, and costs credits and one-shot slots per
attempt. On 2026-10-05 a full day went into art-directing a poster this already
rendered.

    # what can I render?
    python3 campaign-os/scripts/render_post.py --list
    python3 campaign-os/scripts/render_post.py --list --brand stick

    # what does one archetype want?
    python3 campaign-os/scripts/render_post.py --brand swing-shack \\
        --archetype ss-service-promo --describe

    # render it
    python3 campaign-os/scripts/render_post.py --brand swing-shack \\
        --archetype ss-service-promo --channels instagram \\
        --field caption_hook="HIT MORE GREENS" --field cta="BOOK ONLINE" \\
        --field service_label="IRON FITTING" --out out/

    # render a whole week from one JSON file
    python3 campaign-os/scripts/render_post.py --batch week.json --out out/

Batch file shape — a list of posts:
    [{"brand": "stick", "archetype": "stick-shop-corner",
      "channels": ["instagram"], "slug": "mon-psycho-bunny",
      "photo": "data/brand-directory/stick/images/Products/x.jpg",
      "fields": {"caption_hook": "..."}}]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import archetypes as arch_mod  # noqa: E402
from _lib.archetype_compose import compose_post_for_channels  # noqa: E402

BRAND_DIR = REPO / "data" / "brand-directory"


def _brands() -> list[str]:
    return sorted(
        d.name for d in BRAND_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_")
        and (d / "visual-spec" / "archetypes.json").exists()
    )


def _get(brand: str, archetype_id: str) -> dict:
    doc = arch_mod.load_archetypes_doc(brand)
    arc = next((a for a in doc.get("archetypes", []) if a.get("id") == archetype_id), None)
    if not arc:
        ids = [a.get("id") for a in doc.get("archetypes", [])]
        raise SystemExit(f"no archetype {archetype_id!r} for {brand}. Known: {ids}")
    return arc


def cmd_list(brand: str | None) -> int:
    for b in ([brand] if brand else _brands()):
        doc = arch_mod.load_archetypes_doc(b)
        arcs = doc.get("archetypes", [])
        renderable = [a for a in arcs if a.get("template_pack")]
        print(f"\n{b}  ({len(renderable)} renderable of {len(arcs)})")
        for a in arcs:
            pack = a.get("template_pack")
            if not pack:
                print(f"    -  {a['id']:<28} (no template pack — cannot render)")
                continue
            applies = a.get("applies_to") or {}
            photo = "photo required" if applies.get("needs_photo") else "no photo needed"
            chans = ",".join(applies.get("channels") or [])
            print(f"    ok {a['id']:<28} {photo:<16} {chans}")
    return 0


def cmd_describe(brand: str, archetype_id: str) -> int:
    arc = _get(brand, archetype_id)
    doc = arch_mod.load_archetypes_doc(brand)
    canvas = (doc.get("canvases") or {}).get(arc.get("canvas") or "") or {}
    applies = arc.get("applies_to") or {}
    print(f"{brand}/{archetype_id}")
    print(f"  {arc.get('name','')}")
    print(f"  canvas        {arc.get('canvas')} "
          f"{canvas.get('w')}x{canvas.get('h')} ({canvas.get('aspect')})")
    print(f"  channels      {', '.join(applies.get('channels') or [])}")
    print(f"  needs photo   {bool(applies.get('needs_photo'))}")
    print(f"  template pack {arc.get('template_pack')}")
    pack = REPO / "data" / "brand-directory" / brand / (arc.get("template_pack") or "")
    photos = pack / "photos"
    if photos.is_dir():
        imgs = [f.name for f in sorted(photos.iterdir())
                if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
        print(f"  pack photos   {len(imgs)}" + (f" (e.g. {imgs[0]})" if imgs else ""))
    print("\n  fields to supply (--field key=value):")
    for zname, zone in (arc.get("zones") or {}).items():
        if zone.get("kind") != "text":
            continue
        src = zone.get("source") or zname
        if src == "static":
            print(f"    {zname:<16} (static — the template supplies this)")
            continue
        budget = ""
        if zone.get("max_chars_per_line"):
            budget = (f"up to {zone.get('max_lines') or 1} line(s) x "
                      f"{zone['max_chars_per_line']} chars")
        suffix = zone.get("text_suffix")
        note = f"  template appends {suffix!r} — do not include it" if suffix else ""
        print(f"    {src:<16} {budget}{note}")
    return 0


def _pick_photo(brand: str, arc: dict, explicit: str | None, seed: int | None) -> bytes | None:
    """Explicit path wins; otherwise take one from the archetype's own pack."""
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = REPO / p
        if not p.is_file():
            raise SystemExit(f"photo not found: {p}")
        return p.read_bytes()
    pack = arc.get("template_pack")
    if not pack:
        return None
    # photos/ only. references/ holds FINISHED posts with the brand plate and
    # headline already baked in; compositing on top of one double-prints the
    # lockup and the headline. zen-venue-promo currently ships such a post as
    # its photos/ plate, so even photos/ is worth a glance before trusting it.
    d = REPO / "data" / "brand-directory" / brand / pack / "photos"
    if d.is_dir():
        imgs = [f for f in sorted(d.iterdir())
                if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
        if imgs:
            if seed is not None:
                return random.Random(seed).choice(imgs).read_bytes()
            return imgs[0].read_bytes()
    return None


def runtime_data_dir() -> Path:
    """Where the app reads runtime assets from.

    Prod sets DATA_DIR to the Railway volume. With it unset, the app writes
    local runtime state into campaign-os/data/ (gitignored), so publishing
    there is what a local dashboard will actually serve.
    """
    env = os.environ.get("DATA_DIR")
    if env:
        return Path(env)
    return CAMPAIGN_OS / "data"


def publish_into_campaign_os(brand: str, slug: str, channel: str, png: bytes) -> dict[str, str]:
    """Put one rendered post where Campaign OS serves it from.

    Writes the PNG plus an IG/FB-tuned JPEG into
    <DATA_DIR>/draft-assets/images/<brand>/, which /brand-images/<brand>/<file>
    already falls back to. Uses _lib.publish_image so the JPEG matches what the
    rest of the pipeline produces (4:4:4, quality 95) rather than a second
    encoder with its own settings.
    """
    from _lib.publish_image import (  # noqa: PLC0415
        publish_jpeg_name_for_png,
        write_publish_jpeg_from_png_bytes,
    )

    out_dir = runtime_data_dir() / "draft-assets" / "images" / brand
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"composed-{slug}-{channel}.png"
    png_path.write_bytes(png)
    jpg_path = out_dir / publish_jpeg_name_for_png(png_path.name)
    write_publish_jpeg_from_png_bytes(png, jpg_path)
    return {
        "png": str(png_path),
        "jpg": str(jpg_path),
        "url": f"/brand-images/{brand}/{png_path.name}",
    }


def render_one(spec: dict, out_dir: Path, *, seed: int | None = None,
               publish: bool = False) -> list[Path]:
    brand = spec["brand"]
    arc = _get(brand, spec["archetype"])
    applies = arc.get("applies_to") or {}
    channels = spec.get("channels") or applies.get("channels") or ["instagram"]
    photo = _pick_photo(brand, arc, spec.get("photo"), seed)
    if applies.get("needs_photo") and photo is None:
        raise SystemExit(
            f"{brand}/{spec['archetype']} needs a photo and its pack has none. "
            f"Pass photo=<path> (try data/brand-directory/{brand}/images/)."
        )
    res = compose_post_for_channels(
        brand_id=brand, archetype=arc, channels=list(channels),
        fields=dict(spec.get("fields") or {}), photo_bytes=photo,
    )
    if not res:
        raise SystemExit(
            f"{brand}/{spec['archetype']} produced nothing for channels {channels}. "
            f"It applies to {applies.get('channels')}."
        )
    slug = spec.get("slug") or spec["archetype"]
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for channel, png in res.items():
        path = out_dir / f"{brand}__{slug}__{channel}.png"
        path.write_bytes(png)
        written.append(path)
        if publish:
            placed = publish_into_campaign_os(brand, slug, channel, png)
            print(f"       -> Campaign OS {placed['url']}")
            print(f"       -> social JPEG {Path(placed['jpg']).name}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list archetypes and whether they render")
    ap.add_argument("--describe", action="store_true", help="show one archetype's fields")
    ap.add_argument("--brand")
    ap.add_argument("--archetype")
    ap.add_argument("--channels", help="comma-separated; defaults to the archetype's own")
    ap.add_argument("--field", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--photo", help="path to a photo; defaults to one from the template pack")
    ap.add_argument("--slug", help="output filename stem")
    ap.add_argument("--batch", help="JSON file holding a list of post specs")
    ap.add_argument("--seed", type=int, help="deterministic photo pick from the pack")
    ap.add_argument("--out", default="out", help="output directory (default: out/)")
    ap.add_argument("--publish", action="store_true",
                    help="also place each post where Campaign OS serves it, "
                         "with an IG/FB-tuned JPEG beside it")
    a = ap.parse_args()

    if a.list:
        return cmd_list(a.brand)
    if a.describe:
        if not (a.brand and a.archetype):
            ap.error("--describe needs --brand and --archetype")
        return cmd_describe(a.brand, a.archetype)

    out_dir = Path(a.out)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir

    if a.batch:
        specs = json.loads(Path(a.batch).read_text())
        if not isinstance(specs, list):
            raise SystemExit("--batch file must hold a JSON list of post specs")
        failures = 0
        for i, spec in enumerate(specs, 1):
            label = f"{spec.get('brand')}/{spec.get('archetype')}"
            try:
                for p in render_one(spec, out_dir, seed=a.seed, publish=a.publish):
                    print(f"  ok   {p.relative_to(REPO)}")
            except SystemExit as e:
                print(f"  FAIL {i}. {label}: {e}")
                failures += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL {i}. {label}: {type(e).__name__}: {e}")
                failures += 1
        print(f"\n{len(specs) - failures}/{len(specs)} rendered into {out_dir.relative_to(REPO)}")
        return failures

    if not (a.brand and a.archetype):
        ap.error("need --brand and --archetype (or --list / --batch)")
    fields = {}
    for pair in a.field:
        if "=" not in pair:
            ap.error(f"--field wants KEY=VALUE, got {pair!r}")
        k, v = pair.split("=", 1)
        fields[k] = v.replace("\\n", "\n")
    spec = {"brand": a.brand, "archetype": a.archetype, "fields": fields,
            "photo": a.photo, "slug": a.slug}
    if a.channels:
        spec["channels"] = [c.strip() for c in a.channels.split(",") if c.strip()]
    for p in render_one(spec, out_dir, seed=a.seed, publish=a.publish):
        print(f"  ok   {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
