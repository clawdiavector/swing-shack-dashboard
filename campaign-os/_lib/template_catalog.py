"""Compose template labels + reference art paths for operator UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _lib.archetypes import _bundled_brand_root, archetype_by_id


def _brand_roots(brand_id: str) -> list[Path]:
    import os

    roots: list[Path] = []
    data_root = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory" / brand_id
    bundled = _bundled_brand_root() / brand_id
    if data_root.is_dir():
        roots.append(data_root.resolve())
    if bundled.is_dir():
        roots.append(bundled.resolve())
    return roots


def _load_spec_at(brand_id: str, rel_dir: str) -> dict[str, Any]:
    rel = rel_dir.strip("/").replace("\\", "/")
    for root in _brand_roots(brand_id):
        path = root / rel / "spec.json"
        if path.is_file():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                return doc if isinstance(doc, dict) else {}
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


def _resolve_reference_path(rel: str, template_pack: str) -> str:
    """Map spec-relative refs (references/ref-01.jpg) to brand-directory paths."""
    path = str(rel or "").strip().lstrip("/").replace("\\", "/")
    if not path or path.startswith("templates/"):
        return path
    pack = str(template_pack or "").strip().strip("/")
    if pack:
        return f"{pack}/{path}"
    return path


def _reference_paths_from_doc(*docs: dict[str, Any], template_pack: str = "") -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        pack = str(doc.get("template_pack") or template_pack or "").strip().strip("/")
        for key in ("measured_from", "references"):
            rows = doc.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                rel = _resolve_reference_path(str(row or ""), pack)
                if not rel or rel in seen:
                    continue
                seen.add(rel)
                out.append(rel)
    return out


def template_label(template_id: str) -> str:
    tid = str(template_id or "").strip()
    if not tid:
        return ""
    for prefix in ("stick-", "ss-", "swing-shack-"):
        if tid.startswith(prefix):
            return tid[len(prefix) :].replace("_", " ")
    parts = tid.split("-", 1)
    return parts[1].replace("_", " ") if len(parts) == 2 else tid.replace("_", " ")


def public_brand_directory_url(brand_id: str, rel_path: str) -> str:
    rel = str(rel_path or "").strip().lstrip("/").replace("\\", "/")
    if not rel:
        return ""
    return f"/brand-directory/{brand_id}/{rel}"


def template_display_meta(brand_id: str, template_id: str) -> dict[str, Any]:
    tid = str(template_id or "").strip()
    if not tid or not brand_id:
        return {}
    arch = archetype_by_id(brand_id, tid) or {}
    spec: dict[str, Any] = {}
    pack = str(arch.get("template_pack") or "").strip().strip("/")
    if pack:
        spec = _load_spec_at(brand_id, pack)
    if not spec:
        slug = template_label(tid).replace(" ", "-")
        spec = _load_spec_at(brand_id, f"templates/{slug}")
    pack = str(arch.get("template_pack") or spec.get("template_pack") or "").strip().strip("/")
    refs = _reference_paths_from_doc(arch, spec, template_pack=pack)
    name = str(arch.get("name") or spec.get("name") or tid).strip()
    label = template_label(tid) or name.split("—")[0].strip()[:48]
    return {
        "template_id": tid,
        "template_name": name,
        "template_label": label,
        "template_reference_urls": [public_brand_directory_url(brand_id, p) for p in refs[:8]],
    }


def resolve_template_id(
    brand_id: str,
    *,
    record: dict[str, Any] | None = None,
    archetype_meta: dict[str, Any] | None = None,
    source_inbox_item_id: str | None = None,
) -> str:
    if record:
        tid = str(record.get("template_id") or record.get("archetype_id") or "").strip()
        if tid:
            return tid
    if isinstance(archetype_meta, dict):
        tid = str(archetype_meta.get("id") or "").strip()
        if tid:
            return tid
    if source_inbox_item_id:
        from _lib.archetypes import _moment_context, select_archetype  # noqa: PLC0415

        ctx = _moment_context(brand_id, source_inbox_item_id)
        tid = str(ctx.get("template_id") or "").strip()
        if tid:
            return tid
        arch = select_archetype(brand_id, source_inbox_item_id)
        return str(arch.get("id") or "").strip()
    return ""


def attach_template_fields(
    brand_id: str,
    target: dict[str, Any],
    *,
    record: dict[str, Any] | None = None,
    archetype_meta: dict[str, Any] | None = None,
    source_inbox_item_id: str | None = None,
) -> None:
    tid = resolve_template_id(
        brand_id,
        record=record,
        archetype_meta=archetype_meta,
        source_inbox_item_id=source_inbox_item_id,
    )
    if not tid:
        return
    target.update(template_display_meta(brand_id, tid))
