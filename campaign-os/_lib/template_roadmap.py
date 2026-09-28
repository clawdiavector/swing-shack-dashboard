"""Template roadmap — expected families vs on-disk packs (coverage matrix)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from _lib import archetypes as arch_lib
from _lib import template_gallery as gallery

_ROADMAP_REL = Path("data") / "campaign-os" / "template-roadmap.yaml"


def _repo_data_roots() -> list[Path]:
    roots: list[Path] = []
    here = Path(__file__).resolve()
    bundled = here.parents[2] / "data" / "campaign-os"
    if bundled.is_dir():
        roots.append(bundled.parent.parent.resolve())
    for root in gallery.brand_directory_roots():
        repo = root.parent.parent
        if repo.is_dir() and repo not in roots:
            roots.append(repo.resolve())
    return roots


def _roadmap_path() -> Path | None:
    for repo in _repo_data_roots():
        cand = repo / _ROADMAP_REL
        if cand.is_file():
            return cand
    fallback = Path(__file__).resolve().parents[2] / _ROADMAP_REL
    return fallback if fallback.is_file() else None


def load_template_roadmap_doc() -> dict[str, Any]:
    path = _roadmap_path()
    if path is None:
        return {"version": 1, "brands": {}}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {"version": 1, "brands": {}}
    return data if isinstance(data, dict) else {"version": 1, "brands": {}}


def roadmap_rows_for_brand(brand_id: str) -> list[dict[str, Any]]:
    doc = load_template_roadmap_doc()
    brands = doc.get("brands") if isinstance(doc.get("brands"), dict) else {}
    block = brands.get(str(brand_id or "").strip()) if isinstance(brands, dict) else None
    if not isinstance(block, dict):
        return []
    rows = block.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and row.get("archetype_id"):
            out.append(dict(row))
    return out


def _archetype_by_id(archetypes: list[Any], archetype_id: str) -> dict[str, Any] | None:
    aid = str(archetype_id or "").strip()
    for arch in archetypes:
        if isinstance(arch, dict) and str(arch.get("id") or "") == aid:
            return arch
    return None


def _has_golden_or_reference(pack_dir: Path | None) -> bool:
    if not pack_dir or not pack_dir.is_dir():
        return False
    for sub in ("golden", "goldens", "references"):
        subdir = pack_dir / sub
        if not subdir.is_dir():
            continue
        for path in subdir.iterdir():
            if path.is_file() and path.suffix.lower() in gallery._IMAGE_EXT:
                return True
    return False


def _resolve_row_status(
    brand_path: Path,
    archetype: dict[str, Any] | None,
    archetype_id: str,
) -> str:
    """ready | partial | missing."""
    if archetype is None:
        slug = archetype_id.split("-", 1)[-1] if "-" in archetype_id else archetype_id
        pack_only = brand_path / "templates" / slug
        if pack_only.is_dir() and (pack_only / "spec.json").is_file():
            return "partial" if not _has_golden_or_reference(pack_only) else "ready"
        return "missing"

    if not gallery._is_compose_template(brand_path, archetype):
        pack_dir = gallery._template_pack_dir(brand_path, archetype)
        if pack_dir and (pack_dir / "spec.json").is_file():
            return "partial"
        if archetype.get("template_pack") or archetype.get("zones"):
            return "partial"
        return "missing"

    spec = gallery._load_spec(brand_path, archetype)
    pack_dir = gallery._template_pack_dir(brand_path, archetype)
    if not spec or not pack_dir:
        return "partial"
    previews = gallery.template_display_meta(
        brand_path.name,
        archetype,
        brand_path,
    )
    if previews and _has_golden_or_reference(pack_dir):
        return "ready"
    if previews or _has_golden_or_reference(pack_dir):
        return "partial"
    return "partial"


def _enrich_coverage_row(
    brand_id: str,
    brand_path: Path,
    row: dict[str, Any],
    archetypes: list[Any],
    selection: dict[str, Any],
) -> dict[str, Any]:
    archetype_id = str(row.get("archetype_id") or "")
    arch = _archetype_by_id(archetypes, archetype_id)
    status = _resolve_row_status(brand_path, arch, archetype_id)
    spec = gallery._load_spec(brand_path, arch) if arch else None
    template_pack = str(
        row.get("template_pack")
        or (arch or {}).get("template_pack")
        or (spec or {}).get("template_pack")
        or ""
    )
    section = str(row.get("section") or "")
    if not section and arch:
        section = gallery._derive_section(archetype_id, template_pack)

    previews: list[str] = []
    description = str(row.get("notes") or "")
    md_excerpt = ""
    name = str(row.get("label") or archetype_id)
    canvas = ""
    needs_photo = False
    zone_keys: list[str] = []
    post_hints: list[str] = []

    if arch and status in ("ready", "partial"):
        previews = gallery.template_display_meta(brand_id, arch, brand_path)
        if spec:
            description = str(spec.get("description") or description).strip() or description
            name = str(spec.get("name") or arch.get("name") or name)
            canvas = str(spec.get("canvas") or arch.get("canvas") or "")
        else:
            name = str(arch.get("name") or name)
            canvas = str(arch.get("canvas") or "")
        applies = arch.get("applies_to") if isinstance(arch.get("applies_to"), dict) else {}
        needs_photo = bool(applies.get("needs_photo"))
        if spec and isinstance(spec.get("applies_to"), dict) and "needs_photo" in spec["applies_to"]:
            needs_photo = bool(spec["applies_to"]["needs_photo"])
        zone_keys = gallery._zone_keys(arch, spec)
        post_hints = gallery._post_type_hints(archetype_id, selection)
        md_excerpt = gallery._template_md_excerpt(brand_path, arch)

    if status == "missing":
        previews = []

    label = str(row.get("label") or "")
    if not label and arch:
        label = gallery.template_label(archetype_id, spec, arch)
    elif not label:
        label = archetype_id

    out: dict[str, Any] = {
        "family_key": str(row.get("family_key") or ""),
        "label": label,
        "archetype_id": archetype_id,
        "section": section or "Other",
        "notes": str(row.get("notes") or ""),
        "status": status,
        "template_id": archetype_id,
        "name": name,
        "description": description,
        "canvas": canvas,
        "needs_photo": needs_photo,
        "post_type_hints": post_hints,
        "sections": zone_keys,
        "preview_urls": previews,
        "template_md_excerpt": md_excerpt,
        "template_pack": template_pack,
    }
    hint = row.get("content_bank_hint")
    if hint:
        out["content_bank_hint"] = str(hint)
    if row.get("wave") is not None:
        out["wave"] = int(row["wave"])
    return out


def build_template_coverage(brand_id: str) -> dict[str, Any]:
    """Merge roadmap YAML with live archetypes + template packs for one brand."""
    bid = str(brand_id or "").strip()
    brand_path = gallery._brand_path(bid)
    if brand_path is None:
        raise ValueError(f"unknown brand_id: {bid}")

    rows_in = roadmap_rows_for_brand(bid)
    doc = arch_lib.load_archetypes_doc(bid)
    archetypes = doc.get("archetypes") or []
    if not isinstance(archetypes, list):
        archetypes = []
    selection = doc.get("selection") if isinstance(doc.get("selection"), dict) else {}

    rows: list[dict[str, Any]] = []
    for row in rows_in:
        rows.append(_enrich_coverage_row(bid, brand_path, row, archetypes, selection))

    summary = {"ready": 0, "partial": 0, "missing": 0, "total": len(rows)}
    for row in rows:
        st = str(row.get("status") or "missing")
        if st in summary:
            summary[st] += 1

    return {
        "brand_id": bid,
        "rows": rows,
        "summary": summary,
    }


def coverage_roadmap_path() -> str | None:
    path = _roadmap_path()
    return str(path) if path else None
