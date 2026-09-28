"""Template gallery — compose templates + condensed brand bible for Results UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from _lib import archetypes as arch_lib
from _lib import brand_directory as brand_dir_mod

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_PREVIEW_SUBDIRS = ("references", "compare-refs", "golden", "goldens")


def brand_directory_roots() -> list[Path]:
    """Runtime DATA_DIR first, then bundled repo data (same as archetypes loader)."""
    roots: list[Path] = []
    data_root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory"
    if data_root.is_dir():
        roots.append(data_root.resolve())
    bundled = Path(__file__).resolve().parents[2] / "data" / "brand-directory"
    if bundled.is_dir():
        bundled_res = bundled.resolve()
        if bundled_res not in roots:
            roots.append(bundled_res)
    env_bundled = os.environ.get("BUNDLED_DATA_DIR")
    if env_bundled:
        eb = Path(env_bundled) / "brand-directory"
        if eb.is_dir():
            eb_res = eb.resolve()
            if eb_res not in roots:
                roots.append(eb_res)
    return roots


def _brand_path(brand_id: str) -> Path | None:
    for root in brand_directory_roots():
        p = root / brand_id
        if p.is_dir():
            return p
    return None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _load_visual_bible(brand_id: str) -> dict[str, Any]:
    for root in brand_directory_roots():
        path = root / brand_id / "bible-visual.json"
        doc = _read_json(path)
        if doc:
            return doc
    return {}


def template_media_url(brand_id: str, relpath: str) -> str:
    rel = str(relpath or "").lstrip("/").replace("\\", "/")
    if rel.startswith("templates/"):
        return f"/brand-directory-media/{brand_id}/{rel}"
    if rel.startswith("brand-directory/"):
        rel = rel.split("brand-directory/", 1)[-1]
        if "/" in rel:
            _, rest = rel.split("/", 1)
            return f"/brand-directory-media/{brand_id}/{rest}"
    return f"/brand-directory-media/{brand_id}/{rel}"


def template_label(template_id: str, spec: dict[str, Any] | None, archetype: dict[str, Any]) -> str:
    if spec and spec.get("name"):
        name = str(spec["name"])
        if "—" in name:
            return name.split("—", 1)[0].strip()
        if " - " in name:
            return name.split(" - ", 1)[0].strip()
        return name[:80]
    if archetype.get("name"):
        name = str(archetype["name"])
        if "—" in name:
            return name.split("—", 1)[0].strip()
        return name[:80]
    slug = str(template_id or "").split("-", 1)[-1]
    return slug.replace("-", " ").title()


def _slug_from_archetype(archetype_id: str, template_pack: str) -> str:
    if template_pack:
        pack = template_pack.strip("/")
        if pack.startswith("templates/"):
            return pack.split("/", 1)[-1]
    parts = str(archetype_id or "").split("-", 1)
    return parts[-1] if len(parts) > 1 else str(archetype_id or "")


def _template_pack_dir(brand_path: Path, archetype: dict[str, Any]) -> Path | None:
    pack = str(archetype.get("template_pack") or "").strip()
    if pack:
        cand = brand_path / pack
        if cand.is_dir():
            return cand
    slug = _slug_from_archetype(str(archetype.get("id") or ""), pack)
    cand = brand_path / "templates" / slug
    if cand.is_dir():
        return cand
    return None


def _load_spec(brand_path: Path, archetype: dict[str, Any]) -> dict[str, Any] | None:
    pack_dir = _template_pack_dir(brand_path, archetype)
    if pack_dir:
        spec = _read_json(pack_dir / "spec.json")
        if spec:
            return spec
    return None


def _is_compose_template(brand_path: Path, archetype: dict[str, Any]) -> bool:
    if not isinstance(archetype, dict):
        return False
    if str(archetype.get("template_pack") or "").strip():
        return True
    slug = _slug_from_archetype(str(archetype.get("id") or ""), "")
    return (brand_path / "templates" / slug / "spec.json").is_file()


def _collect_preview_files(pack_dir: Path | None, measured: list[Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add_path(rel: str) -> None:
        rel = rel.strip().lstrip("/")
        if not rel or rel in seen:
            return
        seen.add(rel)
        urls.append(rel)

    for item in measured or []:
        if not isinstance(item, str):
            continue
        if any(item.lower().endswith(ext) for ext in _IMAGE_EXT):
            add_path(item)

    if pack_dir and pack_dir.is_dir():
        for sub in _PREVIEW_SUBDIRS:
            subdir = pack_dir / sub
            if not subdir.is_dir():
                continue
            for path in sorted(subdir.iterdir()):
                if path.is_file() and path.suffix.lower() in _IMAGE_EXT:
                    add_path(str(path.relative_to(pack_dir.parent.parent)).replace("\\", "/"))
        for single in ("compare-refs.jpg", "compare-sheet.jpg"):
            p = pack_dir / "golden" / single
            if p.is_file():
                add_path(str(p.relative_to(pack_dir.parent.parent)).replace("\\", "/"))

    return urls


def template_display_meta(
    brand_id: str,
    archetype: dict[str, Any],
    brand_path: Path,
) -> list[str]:
    measured = archetype.get("measured_from") or []
    pack_dir = _template_pack_dir(brand_path, archetype)
    rels = _collect_preview_files(pack_dir, measured if isinstance(measured, list) else [])
    out: list[str] = []
    for rel in rels:
        if rel.startswith("templates/"):
            out.append(template_media_url(brand_id, rel))
        elif pack_dir:
            slug = pack_dir.name
            out.append(template_media_url(brand_id, f"templates/{slug}/{rel}"))
    return out


def _post_type_hints(archetype_id: str, selection: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    rules = selection.get("rules") or []
    if not isinstance(rules, list):
        return hints
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("use") or "") != archetype_id:
            continue
        when = rule.get("when") or {}
        if not isinstance(when, dict):
            continue
        pt = when.get("post_type_in")
        if isinstance(pt, list):
            for p in pt:
                s = str(p).strip()
                if s and s not in hints:
                    hints.append(s)
    return hints


def _derive_section(template_id: str, template_pack: str) -> str:
    tid = str(template_id or "").lower()
    pack = str(template_pack or "").lower()
    if "promo" in tid or "sale" in tid or "discount" in tid or "price" in tid or "offer" in tid:
        return "Promo"
    if tid.startswith("ss-") or tid.startswith("swing-shack-"):
        if any(x in tid for x in ("sale", "price", "discount", "promo", "package")):
            return "Promo"
    if "service" in tid or "service" in pack:
        return "Services"
    if "coach" in tid or "staff" in tid:
        return "Coaching"
    if "location" in tid or "drive" in tid:
        return "Location"
    if "shop" in tid:
        return "Shop"
    if "brand" in tid or "statement" in tid:
        return "Brand"
    if "lesson" in tid or "did-you-know" in tid or "fitting" in tid:
        return "Education"
    if pack.startswith("templates/"):
        folder = pack.split("/", 1)[-1]
        if "service" in folder:
            return "Services"
        if "promo" in folder or "sale" in folder:
            return "Promo"
    parts = tid.split("-")
    if len(parts) >= 2:
        return parts[1].replace("_", " ").title()
    return "Other"


def _palette_summary(brand_record: dict[str, Any]) -> list[dict[str, str]]:
    palette = brand_record.get("palette")
    if not isinstance(palette, dict):
        return []
    out: list[dict[str, str]] = []
    for key in ("primary", "accent", "neutral_light", "secondary"):
        row = palette.get(key)
        if isinstance(row, dict) and row.get("hex"):
            out.append(
                {
                    "role": key,
                    "name": str(row.get("name") or key),
                    "hex": str(row["hex"]),
                }
            )
    if out:
        return out
    tokens = (brand_record.get("palette_full") or {}).get("tokens") or {}
    if isinstance(tokens, dict):
        for name, hex_val in list(tokens.items())[:4]:
            if isinstance(hex_val, str) and hex_val.startswith("#"):
                out.append({"role": str(name), "name": str(name), "hex": hex_val})
    return out


def _condensed_bible(bible: dict[str, Any], brand_record: dict[str, Any]) -> dict[str, Any]:
    comp = bible.get("composition_rules") or []
    anti = bible.get("anti_patterns") or []
    return {
        "voice": str(bible.get("voice") or "")[:500],
        "philosophy": str(bible.get("philosophy") or bible.get("visual_philosophy") or "")[:800],
        "composition_rules": [str(x) for x in comp][:12] if isinstance(comp, list) else [],
        "anti_patterns": [str(x) for x in anti][:12] if isinstance(anti, list) else [],
        "palette_summary": _palette_summary(brand_record),
    }


def _template_md_excerpt(brand_path: Path, archetype: dict[str, Any], limit: int = 2000) -> str:
    pack_dir = _template_pack_dir(brand_path, archetype)
    if not pack_dir:
        return ""
    md_path = pack_dir / "template.md"
    if not md_path.is_file():
        return ""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _zone_keys(archetype: dict[str, Any], spec: dict[str, Any] | None) -> list[str]:
    zones = None
    if spec and isinstance(spec.get("zones"), dict):
        zones = spec["zones"]
    elif isinstance(archetype.get("zones"), dict):
        zones = archetype["zones"]
    if not isinstance(zones, dict):
        return []
    return sorted(str(k) for k in zones.keys())


def build_template_gallery(brand_id: str) -> dict[str, Any]:
    """Build gallery payload for a brand. Raises ValueError if brand directory missing."""
    bid = str(brand_id or "").strip()
    brand_path = _brand_path(bid)
    if brand_path is None:
        raise ValueError(f"unknown brand_id: {bid}")

    brand_record = brand_dir_mod.load_brand(bid, base_dir=brand_path.parent)
    bible = _load_visual_bible(bid)
    doc = arch_lib.load_archetypes_doc(bid)
    archetypes = doc.get("archetypes") or []
    selection = doc.get("selection") if isinstance(doc.get("selection"), dict) else {}

    templates: list[dict[str, Any]] = []
    for arch in archetypes:
        if not isinstance(arch, dict):
            continue
        if not _is_compose_template(brand_path, arch):
            continue
        spec = _load_spec(brand_path, arch)
        tid = str(arch.get("id") or (spec.get("id") if spec else "") or "")
        if not tid and spec:
            tid = str(spec.get("id") or "")
        applies = arch.get("applies_to") if isinstance(arch.get("applies_to"), dict) else {}
        needs_photo = bool(applies.get("needs_photo"))
        if spec and isinstance(spec.get("applies_to"), dict) and "needs_photo" in spec["applies_to"]:
            needs_photo = bool(spec["applies_to"]["needs_photo"])
        template_pack = str(arch.get("template_pack") or (spec or {}).get("template_pack") or "")
        description = str(
            (spec or {}).get("description") or arch.get("description") or ""
        ).strip()
        section = _derive_section(tid, template_pack)
        previews = template_display_meta(bid, arch, brand_path)
        templates.append(
            {
                "template_id": tid,
                "name": str((spec or {}).get("name") or arch.get("name") or tid),
                "label": template_label(tid, spec, arch),
                "description": description,
                "canvas": str((spec or {}).get("canvas") or arch.get("canvas") or ""),
                "needs_photo": needs_photo,
                "post_type_hints": _post_type_hints(tid, selection),
                "sections": _zone_keys(arch, spec),
                "preview_urls": previews,
                "template_md_excerpt": _template_md_excerpt(brand_path, arch),
                "section": section,
                "template_pack": template_pack,
            }
        )

    templates.sort(key=lambda t: (t.get("section") or "", t.get("label") or ""))

    by_section: dict[str, list[dict[str, Any]]] = {}
    for row in templates:
        sec = str(row.get("section") or "Other")
        by_section.setdefault(sec, []).append(row)

    section_order = ["Services", "Promo", "Brand", "Shop", "Coaching", "Location", "Education", "Other"]
    sections_out: list[dict[str, Any]] = []
    seen_secs: set[str] = set()
    for sec in section_order:
        if sec in by_section:
            sections_out.append({"section": sec, "templates": by_section[sec]})
            seen_secs.add(sec)
    for sec, rows in sorted(by_section.items()):
        if sec not in seen_secs:
            sections_out.append({"section": sec, "templates": rows})

    from _lib import template_roadmap as _roadmap_mod

    payload: dict[str, Any] = {
        "brand_id": bid,
        "brand_bible": _condensed_bible(bible, brand_record),
        "templates": templates,
        "sections": sections_out,
        "template_count": len(templates),
    }
    payload["coverage"] = _roadmap_mod.build_template_coverage(bid)
    return payload
