#!/usr/bin/env python3
"""Probe the specs this repo is known to drift on, and report PASS/FAIL/SKIP.

Specs here drift from reality silently and nothing checked. Six were found wrong
in a single day on 2026-10-05 by probing live. This is that probing, written
down. Every check is free: no image is generated, no credits are spent, nothing
is posted.

    python3 campaign-os/scripts/verify_specs.py            # all checks
    python3 campaign-os/scripts/verify_specs.py --only krea # substring filter
    python3 campaign-os/scripts/verify_specs.py --json      # machine-readable

Exit status is the number of FAILing checks, so CI can gate on it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
sys.path.insert(0, str(CAMPAIGN_OS))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
_RESULTS: list[dict] = []
_CHECKS: list[tuple[str, str, object]] = []


def check(name: str, claim: str):
    """Register a check. The function returns (status, detail)."""
    def deco(fn):
        _CHECKS.append((name, claim, fn))
        return fn
    return deco


# ── Krea: model ids and the aspect/pixel table ──────────────────────────────

def _krea_rpc(messages: list[dict], timeout: int = 180) -> list[dict]:
    """Drive the stdio bridge, which resolves the token from ~/.krea/mcp.json."""
    proc = subprocess.run(
        [sys.executable, str(CAMPAIGN_OS / "scripts" / "krea_mcp_stdio.py")],
        input="".join(json.dumps(m) + "\n" for m in messages),
        capture_output=True, text=True, timeout=timeout,
    )
    out = []
    for line in proc.stdout.strip().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _krea_call(tool: str, arguments: dict | None = None) -> dict | None:
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "verify-specs", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": tool, "arguments": arguments or {}}},
    ]
    for msg in _krea_rpc(msgs):
        if msg.get("id") == 2:
            return msg
    return None


def _krea_text(resp: dict | None) -> str:
    if not resp or "result" not in resp:
        return ""
    chunks = resp["result"].get("content") or []
    return "\n".join(c.get("text", "") for c in chunks if isinstance(c, dict))


@check("krea.reachable", "The Krea MCP endpoint accepts the token on disk.")
def _krea_reachable():
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "verify-specs", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
    got = _krea_rpc(msgs)
    init = next((m for m in got if m.get("id") == 1), None)
    tools = next((m for m in got if m.get("id") == 2), None)
    if not init or "error" in init:
        return FAIL, f"initialize failed: {(init or {}).get('error', 'no response')}"
    names = [t["name"] for t in (tools or {}).get("result", {}).get("tools", [])]
    return PASS, f"{len(names)} tools; server={init['result'].get('serverInfo', {}).get('name')}"


# Model ids this repo may name without them being a routing target: registry
# rows explicitly marked unverified, and docstrings. Routing targets are the
# defaults and fallbacks that a generate call actually sends.
_ROUTING_SITES = [
    ("_lib/jobs/layer5/draft_oneshot.py", "ONESHOT_DEFAULT_MODEL"),
    ("_lib/jobs/layer5/draft_oneshot.py", "_ONESHOT_FALLBACK_MODEL"),
    ("_lib/creative_director.py", "_IDEOGRAM_3"),
]


def _live_image_models() -> set[str] | None:
    resp = _krea_call("list_models", {})
    text = _krea_text(resp)
    if not text:
        return None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    return {m["id"] for m in doc.get("models", []) if m.get("category") == "image"}


@check("krea.model_ids", "Every model id this repo routes a generate call to exists upstream.")
def _krea_model_ids():
    live = _live_image_models()
    if live is None:
        return SKIP, "could not parse list_models"

    import re
    bad, checked = [], []
    # a) named routing constants
    for rel, const in _ROUTING_SITES:
        body = (CAMPAIGN_OS / rel).read_text(encoding="utf-8", errors="replace")
        m = re.search(rf'^{re.escape(const)}\s*=\s*["\']([^"\']+)["\']', body, re.M)
        if not m:
            continue
        mid = m.group(1)
        checked.append(f"{const}={mid}")
        if mid not in live:
            near = sorted(x for x in live if mid.split("/")[-1].split("-")[0] in x)
            bad.append(f"{rel}:{const} = {mid!r} does not exist (live: {near or 'none similar'})")

    # b) model= defaults and literal krea model strings in the generate path
    for rel in ("_lib/krea_mcp.py", "app.py"):
        body = (CAMPAIGN_OS / rel).read_text(encoding="utf-8", errors="replace")
        for mid in set(re.findall(r'model[\w ]*[:=]\s*["\']([a-z0-9][a-z0-9/.\-]{3,40})["\']', body)):
            if not any(k in mid for k in ("ideogram", "flux", "recraft", "krea-2", "seedream")):
                continue
            checked.append(f"{rel}:{mid}")
            if mid not in live:
                near = sorted(x for x in live if mid.split("/")[-1].split("-")[0] in x)
                bad.append(f"{rel} sends model={mid!r}, not in the live catalogue (live: {near or 'none similar'})")

    if bad:
        return FAIL, f"{len(live)} live image models; " + " | ".join(bad)
    return PASS, f"{len(checked)} routing ids all live: {checked}"


@check("krea.aspect_pixels", "_KREA_ASPECT_PIXELS maps 4:5 to a size Krea accepts.")
def _krea_aspect():
    from _lib.krea_mcp import _KREA_ASPECT_PIXELS, normalize_krea_aspect
    issues = []
    for ratio, (w, h) in _KREA_ASPECT_PIXELS.items():
        if ":" not in ratio:
            continue
        try:
            a, b = (float(x) for x in ratio.split(":"))
        except ValueError:
            continue
        want, got = a / b, w / h
        if abs(want - got) / want > 0.02:
            issues.append(f"{ratio} -> {w}x{h} (ratio {got:.3f}, expected {want:.3f})")
    norm = normalize_krea_aspect("1024x1280")
    if norm != "4:5":
        issues.append(f"normalize_krea_aspect('1024x1280') == {norm!r}, expected '4:5'")
    if issues:
        return FAIL, "; ".join(issues)
    return PASS, f"{len(_KREA_ASPECT_PIXELS)} ratios internally consistent; 4:5 -> {_KREA_ASPECT_PIXELS['4:5']}"


# ── Brand data and templates ────────────────────────────────────────────────

@check("archetypes.load", "Every brand's archetypes.json parses and has canvases.")
def _archetypes_load():
    from _lib import archetypes
    rows, bad = [], []
    for brand_dir in sorted((REPO / "data" / "brand-directory").iterdir()):
        if not brand_dir.is_dir() or brand_dir.name.startswith("_"):
            continue
        if not (brand_dir / "visual-spec" / "archetypes.json").exists():
            continue
        doc = archetypes.load_archetypes_doc(brand_dir.name)
        arcs = doc.get("archetypes") or []
        if not arcs:
            bad.append(f"{brand_dir.name}: no archetypes parsed")
            continue
        # Only brands that actually render need a canvases block; a brand with no
        # template pack anywhere is a stub and is reported, not failed.
        if not any(a.get("template_pack") for a in arcs):
            rows.append(f"{brand_dir.name}={len(arcs)} (stub, no template packs)")
            continue
        if not doc.get("canvases"):
            bad.append(f"{brand_dir.name}: renders template packs but has no canvases block")
        else:
            rows.append(f"{brand_dir.name}={len(arcs)}")
    if bad:
        return FAIL, "; ".join(bad)
    return PASS, ", ".join(rows)


@check("ss-service-promo.partner_logo", "ss-service-promo carries the partner-logo zone the real posts show.")
def _service_promo_zone():
    from _lib import archetypes
    doc = archetypes.load_archetypes_doc("swing-shack")
    arc = next((a for a in doc.get("archetypes", []) if a["id"] == "ss-service-promo"), None)
    if not arc:
        return FAIL, "ss-service-promo not found"
    zones = arc.get("zones") or {}
    logo_zones = [k for k, v in zones.items()
                  if "logo" in k.lower() or (v.get("kind") == "image" and "logo" in str(v).lower())]
    if not logo_zones:
        return FAIL, (f"no partner-logo zone; zones are {sorted(zones)}. "
                      "Real Services posts put a partner mark beside the lockup.")
    return PASS, f"partner-logo zone present: {logo_zones}"


# Plausible filler per zone source, so a render failure means the template is
# broken rather than that this check guessed the wrong field names.
_FILLER = {
    "caption_hook": "IRON FITTING", "headline": "IRON FITTING",
    "cta": "BOOK ONLINE", "service_label": "IRON FITTING",
    "subhead": "BOOK ONLINE", "body": "TrackMan shows you the gap.",
    "price": "R450", "price_period": "PER SESSION", "code": "SWING10",
    "kicker": "NEW", "qualifier": "60 MIN SESSION",
    "price_labels": "IRON FITTING\nDRIVER FITTING\nPUTTER FITTING",
    "price_values": "R450\nR550\nR350",
    "url": "swingshack.co.za", "offer": "20% OFF", "terms": "T&Cs apply",
}


def _fields_for(arc: dict) -> dict[str, str]:
    """Fill every text zone's declared source with content shaped like that zone.

    Filler that overflows a box would report a working template as broken, so
    each value is cut to the zone's own max_chars_per_line / max_lines budget.
    """
    out = dict(_FILLER)
    for name, zone in (arc.get("zones") or {}).items():
        if zone.get("kind") != "text":
            continue
        src = zone.get("source") or name
        if src == "static":
            continue  # the template supplies its own copy
        if src not in out:
            out[src] = "BETTER BEGINS HERE"
        per_line = zone.get("max_chars_per_line")
        max_lines = zone.get("max_lines") or 1
        if per_line:
            lines = [ln[:per_line] for ln in str(out[src]).split("\n")][:max_lines]
            out[src] = "\n".join(lines)
    return out


def _photo_for(brand: str, arc: dict) -> bytes | None:
    """First photo from the archetype's own template pack, if it has one."""
    pack = arc.get("template_pack")
    if not pack:
        return None
    base = REPO / "data" / "brand-directory" / brand / pack
    for sub in ("photos", "references", "."):
        d = base / sub
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                return f.read_bytes()
    return None


@check("archetypes.declared_budget",
       "Copy filled to each zone's declared max_lines x max_chars_per_line still renders.")
def _declared_budget():
    """Ask the composer, not the font metrics.

    The zone rects were measured from visible ink in real posts, so box height is
    roughly cap height rather than full line pitch; comparing either max_lines or
    max_chars_per_line against those rects with font metrics mis-reports working
    templates. What the declared budget actually promises is that copy of that
    size lays out, so fill every text zone to exactly its budget and see whether
    compose accepts it. A failure here is a budget the template cannot honour.
    """
    from _lib import archetypes
    from _lib.archetype_compose import compose_post_for_channels

    bad, ok = [], []
    for brand in ("swing-shack", "stick"):
        doc = archetypes.load_archetypes_doc(brand)
        for arc in doc.get("archetypes", []):
            if not arc.get("template_pack"):
                continue
            photo = _photo_for(brand, arc)
            if (arc.get("applies_to") or {}).get("needs_photo") and photo is None:
                continue
            fields: dict[str, str] = {}
            for zname, zone in (arc.get("zones") or {}).items():
                if zone.get("kind") != "text":
                    continue
                src = zone.get("source") or zname
                if src == "static":
                    continue
                per_line = zone.get("max_chars_per_line")
                lines = zone.get("max_lines") or 1
                if not per_line:
                    fields.setdefault(src, _FILLER.get(src, "BETTER BEGINS HERE"))
                    continue
                # Uppercase 'N' runs: representative width, and every template
                # here uppercases anyway.
                fields[src] = "\n".join("N" * per_line for _ in range(lines))
            chans = (arc.get("applies_to") or {}).get("channels") or ["instagram"]
            label = f"{brand}/{arc['id']}"
            try:
                compose_post_for_channels(
                    brand_id=brand, archetype=arc, channels=[chans[0]],
                    fields=fields, photo_bytes=photo)
                ok.append(label)
            except Exception as e:  # noqa: BLE001
                worst = max(
                    ((z.get("max_lines") or 1) * (z.get("max_chars_per_line") or 0), n)
                    for n, z in (arc.get("zones") or {}).items()
                    if z.get("kind") == "text"
                )
                bad.append(f"{label}: {type(e).__name__}: {e} "
                           f"(largest budget: {worst[1]} at {worst[0]} chars)")
    if bad:
        return FAIL, (f"{len(ok)} honour their declared budget, {len(bad)} do not. "
                      f"Filled with 'N' (a wide cap), so these are the limits copy "
                      f"generation must not trust: " + " | ".join(bad[:6]))
    return PASS, f"all {len(ok)} archetypes honour their declared copy budget"


@check("templates.render", "Every archetype with a template pack composes to a real PNG.")
def _templates_render():
    from _lib import archetypes
    from _lib.archetype_compose import compose_post_for_channels
    ok, failed, skipped = [], [], []
    for brand in ("swing-shack", "stick"):
        doc = archetypes.load_archetypes_doc(brand)
        for arc in doc.get("archetypes", []):
            if not arc.get("template_pack"):
                continue
            chans = (arc.get("applies_to") or {}).get("channels") or ["instagram"]
            photo = _photo_for(brand, arc)
            needs_photo = (arc.get("applies_to") or {}).get("needs_photo")
            label = f"{brand}/{arc['id']}"
            if needs_photo and photo is None:
                skipped.append(f"{label}: needs a photo, pack has none")
                continue
            try:
                res = compose_post_for_channels(
                    brand_id=brand, archetype=arc, channels=[chans[0]],
                    fields=_fields_for(arc), photo_bytes=photo)
                img = next(iter(res.values()), b"") if res else b""
                if len(img) < 2000 or not img.startswith(b"\x89PNG"):
                    failed.append(f"{label}: {len(img)}B, not a PNG")
                else:
                    ok.append(label)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{label}: {type(e).__name__}: {e}")
    tail = f" ({len(skipped)} skipped: {'; '.join(skipped)})" if skipped else ""
    if failed:
        return FAIL, f"{len(ok)} rendered, {len(failed)} failed -> " + " | ".join(failed[:8]) + tail
    return PASS, f"{len(ok)} archetypes rendered{tail}"


# ── Known-wrong code paths ──────────────────────────────────────────────────

@check("brand_dna.city", "build_system_message() does not hardcode one brand's city onto all brands.")
def _brand_dna_city():
    from _lib import brand_dna
    offenders = []
    for brand, expect_absent in (("stick", "Johannesburg"), ("bag-drop", None)):
        try:
            ctx = brand_dna.load_brand_context(brand)
            msg = brand_dna.build_system_message(ctx)
        except Exception as e:  # noqa: BLE001
            return SKIP, f"{brand}: {type(e).__name__}: {e}"
        if expect_absent and expect_absent in msg:
            offenders.append(f"{brand} system message says {expect_absent!r} (Stick is in Paarl, Western Cape)")
        if "indoor golf studio" in msg and brand == "stick":
            offenders.append("stick described as an 'indoor golf studio' (it is a retail + fitting store)")
    if offenders:
        return FAIL, "; ".join(offenders)
    return PASS, "no cross-brand city or venue-type leak"


@check("image_gen_router.references", "Reference images survive the router instead of being dropped.")
def _router_references():
    from _lib import image_gen_router as igr
    src = (CAMPAIGN_OS / "_lib" / "image_gen_router.py").read_text(encoding="utf-8")
    if "reference_dropped" not in src:
        return SKIP, "no reference_dropped flag in the router to assert on"
    if not hasattr(igr, "_inject_openrouter_references"):
        return FAIL, "reference injection helper is gone; references cannot reach the model"
    msgs = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
    before = json.dumps(msgs)
    try:
        msgs = igr._inject_openrouter_references(
            msgs,
            reference_bytes=[b"\x89PNG\r\n\x1a\n" + b"0" * 64],
            reference_note="match this",
        )
    except Exception as e:  # noqa: BLE001
        return FAIL, f"injection raised {type(e).__name__}: {e}"
    after = json.dumps(msgs)
    if after == before:
        return FAIL, "injecting a reference changed nothing — the image never reaches the payload"
    if "image_url" not in after:
        return FAIL, "no image_url chunk added by reference injection"
    return PASS, "reference bytes reach the message payload as an image_url chunk"


@check("audit_social.reels", "Reels and video get a metric set, not the image one.")
def _audit_reels():
    sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_audit_social", CAMPAIGN_OS / "scripts" / "audit_social.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    table = getattr(mod, "METRICS_BY_MEDIA_TYPE", None)
    if not table:
        return FAIL, "no METRICS_BY_MEDIA_TYPE: one metric set is being used for every media type"
    missing = [t for t in ("IMAGE", "CAROUSEL_ALBUM", "VIDEO", "REELS") if t not in table]
    if missing:
        return FAIL, f"no metric set for {missing}; those posts return no insights"
    if "views" not in table.get("REELS", ""):
        return FAIL, "REELS metric set has no view metric"
    return PASS, f"metric sets for {sorted(table)}"


# ── Drive roots ─────────────────────────────────────────────────────────────

@check("drive.roots", "Each brand's canonical Drive root lists and still holds its imagery.")
def _drive_roots():
    import importlib.util
    from _lib import google_drive as gd
    spec = importlib.util.spec_from_file_location(
        "_ingest", CAMPAIGN_OS / "scripts" / "ingest_public_drive_folder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    roots = getattr(mod, "BRAND_PUBLIC_ROOTS", None)
    if not roots:
        return FAIL, "no BRAND_PUBLIC_ROOTS table; --folder-id falls back to one brand's root"
    rows, bad = [], []
    for brand, fid in sorted(roots.items()):
        try:
            entries = gd.list_public_folder(fid)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{brand} ({fid}): {type(e).__name__}: {e}")
            continue
        imgs = [e for e in entries if gd.is_public_drive_image(e)]
        if not imgs:
            bad.append(f"{brand} ({fid}): lists but holds no images — wrong or emptied folder")
        else:
            rows.append(f"{brand}={len(imgs)}")
    if bad:
        return FAIL, "; ".join(bad)
    return PASS, ", ".join(rows)


# Parent share link, and the Stick location folder that looks like a second
# root. Image-id comparison on 2026-10-05: parent == union of BRAND_PUBLIC_ROOTS;
# the location id is entirely inside Stick. Locked here so the map cannot drop
# them while the code keeps ingesting the children.
_DRIVE_PARENT_ID = "1-zxzR3aYVgfIgLGF-nHHssM_N6zunGOL"
_DRIVE_STICK_LOCATION_SUBSET_ID = "1WIYGaZAPCJvqIDyatroENqx-4DqCNgMz"


@check("drive.map_names_roots",
       "campaign-os-map names the parent share folder and every ingest root.")
def _drive_map_names_roots():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_ingest_map", CAMPAIGN_OS / "scripts" / "ingest_public_drive_folder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    roots = getattr(mod, "BRAND_PUBLIC_ROOTS", None) or {}
    if not roots:
        return FAIL, "no BRAND_PUBLIC_ROOTS table to compare against the map"
    # The map skill ships in the campaign-os plugin; it lived under .claude/skills/
    # until 2026-10-06, so accept the old location too for older checkouts.
    candidates = (
        REPO / "plugins" / "campaign-os" / "skills" / "campaign-os-map" / "SKILL.md",
        REPO / ".claude" / "skills" / "campaign-os-map" / "SKILL.md",
    )
    map_path = next((c for c in candidates if c.is_file()), None)
    if map_path is None:
        return FAIL, "map missing at " + " or ".join(str(c) for c in candidates)
    text = map_path.read_text()
    required = {
        "parent": _DRIVE_PARENT_ID,
        "stick-location-subset": _DRIVE_STICK_LOCATION_SUBSET_ID,
    }
    required.update({f"ingest:{brand}": fid for brand, fid in roots.items()})
    missing = [f"{name} {fid}" for name, fid in sorted(required.items()) if fid not in text]
    if missing:
        return FAIL, "campaign-os-map omits " + "; ".join(missing)
    return PASS, f"map names {len(required)} folder ids"


@check("drive.ingested_images_usable",
       "Ingested images open in PIL, so the composer can actually use them.")
def _dna_errors():
    """dissect() records a failure as an `error` field inside the .visual-dna.json
    rather than raising, so the ingest summary reports dissect_errors: [] and the
    files look fine. Two different failures hide there and they need different
    fixes, so this check opens each one rather than trusting the error string:

      - the file cannot be decoded at all (the 24 HEIC walkthrough photos in
        Stick's Location folder — PIL has no HEIF support here, so these are
        unusable as background photography until converted);
      - the file opens but dissect choked on it (the 12 DJI photos in
        Photos of iron sets are MPO, not plain JPEG, and dissect raises
        KeyError 'colors' on them — the pixels are fine, the tagging is not).
    """
    from PIL import Image, UnidentifiedImageError

    rows, unopenable, dissect_only = [], [], []
    for brand in ("stick", "swing-shack"):
        root = REPO / "data" / "brand-directory" / brand / "images"
        if not root.is_dir():
            continue
        dnas = list(root.rglob("*.visual-dna.json"))
        errs = 0
        for d in dnas:
            try:
                doc = json.loads(d.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not doc.get("error"):
                continue
            errs += 1
            img = Path(doc.get("image_path") or "")
            ext = img.suffix.lower() or "?"
            try:
                with Image.open(img) as im:
                    im.load()
                dissect_only.append((brand, ext, str(doc["error"])[:40]))
            except (UnidentifiedImageError, OSError, ValueError):
                unopenable.append((brand, ext))
        rows.append(f"{brand}: {len(dnas) - errs}/{len(dnas)} dissected clean")

    def _tally(pairs, keyfn):
        out: dict[str, int] = {}
        for row in pairs:
            out[keyfn(row)] = out.get(keyfn(row), 0) + 1
        return ", ".join(f"{n} x {k}" for k, n in sorted(out.items()))

    problems = []
    if unopenable:
        problems.append(f"{len(unopenable)} cannot be decoded at all "
                        f"({_tally(unopenable, lambda r: f'{r[0]} {r[1]}')})")
    if dissect_only:
        problems.append(f"{len(dissect_only)} open but dissect failed "
                        f"({_tally(dissect_only, lambda r: f'{r[0]} {r[1]} {r[2]}')})")
    if problems:
        return FAIL, "; ".join(problems) + ". " + ", ".join(rows)
    return PASS, ", ".join(rows)


@check("drive.manifest_matches_disk", "The ingest manifest describes files that are actually on disk.")
def _manifest_disk():
    bad, rows = [], []
    for brand in ("stick", "swing-shack"):
        mpath = REPO / "data" / "brand-directory" / brand / "ingest-manifest.json"
        if not mpath.exists():
            continue
        images = json.loads(mpath.read_text()).get("images", {})
        root = REPO / "data" / "brand-directory" / brand / "images"
        absent = [k for k in images if not (root / k).exists()]
        rows.append(f"{brand}: {len(images) - len(absent)}/{len(images)} present")
        if absent:
            bad.append(f"{brand}: {len(absent)} manifest entries have no file "
                       f"(e.g. {absent[:3]})")
    if bad:
        return FAIL, "; ".join(bad)
    return PASS, ", ".join(rows)


# ── Runner ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="run only checks whose name contains this substring")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    selected = [c for c in _CHECKS if not args.only or args.only in c[0]]
    if not selected:
        print(f"no checks match {args.only!r}. Known: {', '.join(c[0] for c in _CHECKS)}")
        return 0

    width = max(len(c[0]) for c in selected)
    for name, claim, fn in selected:
        t0 = time.time()
        try:
            status, detail = fn()
        except Exception as e:  # noqa: BLE001 - a broken check must not hide the rest
            status, detail = SKIP, f"check itself raised {type(e).__name__}: {e}"
        row = {"check": name, "claim": claim, "status": status,
               "detail": detail, "seconds": round(time.time() - t0, 2)}
        _RESULTS.append(row)
        if not args.as_json:
            mark = {PASS: "ok  ", FAIL: "FAIL", SKIP: "skip"}[status]
            print(f"{mark} {name:<{width}}  {detail}")

    failures = [r for r in _RESULTS if r["status"] == FAIL]
    if args.as_json:
        print(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "passed": sum(r["status"] == PASS for r in _RESULTS),
                          "failed": len(failures),
                          "skipped": sum(r["status"] == SKIP for r in _RESULTS),
                          "results": _RESULTS}, indent=2))
    else:
        print(f"\n{sum(r['status'] == PASS for r in _RESULTS)} passed, "
              f"{len(failures)} failed, "
              f"{sum(r['status'] == SKIP for r in _RESULTS)} skipped")
        for r in failures:
            print(f"\n  {r['check']}\n    claim:  {r['claim']}\n    actual: {r['detail']}")
    return len(failures)


if __name__ == "__main__":
    raise SystemExit(main())
