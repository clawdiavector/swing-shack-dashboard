"""Single visual trust gate — computed gaps, no silent fallbacks."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from _lib.archetypes import _moment_context, load_archetypes_doc, select_archetype_explained
from _lib.brand_overlay import _candidate_brand_dirs

PhotoKind = Literal["render_spec", "sidecar", "library"]
BackgroundKind = Literal["none", "real_photo", "generated_background"]
DecisionStatus = Literal["trusted", "gap"]

_STANDIN_RE = re.compile(r"^(standin|stand-in|stand_in)[-_]", re.IGNORECASE)
_PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_IMAGE_QUEUE_ACTIONS = frozenset(
    {"draft_photo", "draft_image", "draft_gen_slots", "draft_oneshot", "compose_post"}
)


@dataclass(frozen=True)
class PhotoSource:
    kind: PhotoKind
    path: str


@dataclass(frozen=True)
class VisualDecision:
    status: DecisionStatus
    post_type: str
    archetype_id: str | None
    photo: PhotoSource | None
    background: BackgroundKind
    reason: str
    label: str

    def is_gap(self) -> bool:
        return self.status == "gap"

    def as_gap_payload(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "label": self.label,
            "post_type": self.post_type,
            "archetype_id": self.archetype_id,
        }


def is_stand_in(path: str | Path) -> bool:
    p = Path(str(path))
    if "references" in {part.lower() for part in p.parts}:
        return True
    return bool(_STANDIN_RE.match(p.name))


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _calendar_record(brand_id: str, item_id: str, record: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    if not item_id.startswith("calendar_candidate:"):
        return {}
    from _lib.unified_inbox import _calendar_record_for_key  # noqa: PLC0415

    parts = item_id.split(":", 2)
    if len(parts) < 3:
        return {}
    found = _calendar_record_for_key(brand_id, parts[2])
    return found if isinstance(found, dict) else {}


def _post_type_for_label(record: dict[str, Any], ctx: dict[str, Any]) -> str:
    pt = str(record.get("post_type") or ctx.get("post_type") or "").strip().lower()
    if pt:
        return pt
    pillars = record.get("pillars")
    if isinstance(pillars, list) and pillars:
        return str(pillars[0]).strip().lower()
    pillar_in = ctx.get("pillar_in") or []
    if isinstance(pillar_in, list) and pillar_in:
        return str(pillar_in[0]).strip().lower()
    return "this post"


def _archetype_short_label(archetype: dict[str, Any]) -> str:
    raw = str(archetype.get("name") or archetype.get("id") or "template").strip()
    if "—" in raw:
        return raw.split("—", 1)[0].strip()
    if " - " in raw:
        return raw.split(" - ", 1)[0].strip()
    return raw


def _golden_nonempty(brand_id: str, template_pack: str) -> bool:
    rel = template_pack.strip().strip("/")
    if not rel:
        return False
    for root in _candidate_brand_dirs(brand_id):
        golden = root / rel / "golden"
        if not golden.is_dir():
            continue
        for p in golden.iterdir():
            if p.is_file() and not p.name.startswith("."):
                return True
    return False


def _photos_manifest_real(brand_id: str, library_rel: str) -> set[str] | None:
    rel_dir = library_rel.strip().strip("/")
    if not rel_dir:
        return None
    for root in _candidate_brand_dirs(brand_id):
        manifest = root / rel_dir / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        real = doc.get("real")
        if isinstance(real, list):
            return {str(x).strip() for x in real if str(x).strip()}
    return None


def list_trusted_library_photos(brand_id: str, library_rel: str) -> list[Path]:
    """Real library files only — no stand-ins, no references/."""
    rel_dir = library_rel.strip().strip("/")
    if not rel_dir:
        return []
    allow = _photos_manifest_real(brand_id, rel_dir)
    merged: dict[str, Path] = {}
    for root in _candidate_brand_dirs(brand_id):
        base = root / rel_dir
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if not p.is_file() or p.suffix.lower() not in _PHOTO_SUFFIXES:
                continue
            if allow is not None:
                if p.name in allow:
                    merged.setdefault(p.name, p)
            elif not is_stand_in(p):
                merged.setdefault(p.name, p)
    return sorted(merged.values(), key=lambda x: x.name)


def _sidecar_for_item(item_id: str) -> dict[str, Any] | None:
    from _lib.jobs.layer5.draft_assets import _sidecar_for_moment  # noqa: PLC0415

    return _sidecar_for_moment(item_id)


def _photo_from_sidecar(sidecar: dict[str, Any]) -> PhotoSource | None:
    venue = sidecar.get("venue_photo")
    if venue:
        path = Path(str(venue))
        if not path.is_file():
            alt = _data_dir() / str(venue).lstrip("/")
            path = alt if alt.is_file() else path
        if path.is_file() and not is_stand_in(path):
            return PhotoSource(kind="sidecar", path=str(path))
    qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
    candidates = sidecar.get("photo_candidates") if isinstance(sidecar.get("photo_candidates"), list) else []
    if candidates:
        sel = qc.get("selected")
        idx = int(sel if sel is not None else 0)
        if 0 <= idx < len(candidates):
            path = Path(str(candidates[idx].get("path") or ""))
            if not path.is_file():
                alt = _data_dir() / str(candidates[idx].get("path") or "").lstrip("/")
                path = alt if alt.is_file() else path
            if path.is_file() and not is_stand_in(path):
                return PhotoSource(kind="sidecar", path=str(path))
    return None


def _photo_from_render_spec(record: dict[str, Any]) -> PhotoSource | None:
    rs = record.get("render_spec")
    if not isinstance(rs, dict):
        return None
    photo = rs.get("photo")
    if isinstance(photo, str) and photo.strip():
        path = Path(photo.strip())
        if not path.is_file():
            path = _data_dir() / photo.strip().lstrip("/")
        if path.is_file() and not is_stand_in(path):
            return PhotoSource(kind="render_spec", path=str(path))
    image = rs.get("image")
    if isinstance(image, str) and image.strip():
        try:
            from _lib.jobs.layer5.render_batch import resolve_upload  # noqa: PLC0415

            path = resolve_upload(image.strip())
        except (ValueError, OSError):
            return None
        if path.is_file() and not is_stand_in(path):
            return PhotoSource(kind="render_spec", path=str(path))
    return None


def _photo_from_library(brand_id: str, archetype: dict[str, Any]) -> PhotoSource | None:
    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    library = bg.get("library")
    if not isinstance(library, str) or not library.strip():
        return None
    files = list_trusted_library_photos(brand_id, library)
    if not files:
        return None
    return PhotoSource(kind="library", path=str(files[0]))


def _allow_oneshot() -> bool:
    return str(os.environ.get("COS_ALLOW_ONESHOT") or "").strip() in ("1", "true", "yes")


def _gap(
    *,
    post_type: str,
    archetype_id: str | None,
    reason: str,
    label: str,
    background: BackgroundKind = "none",
) -> VisualDecision:
    return VisualDecision(
        status="gap",
        post_type=post_type,
        archetype_id=archetype_id,
        photo=None,
        background=background,
        reason=reason,
        label=label,
    )


def decide(brand_id: str, item_id: str, *, record: dict[str, Any] | None = None) -> VisualDecision:
    """Pure trust decision for a calendar moment (no network, no generation)."""
    cal = _calendar_record(brand_id, item_id, record)
    ctx = _moment_context(brand_id, item_id)
    post_type = _post_type_for_label(cal, ctx)

    if not item_id.startswith("calendar_candidate:"):
        return VisualDecision(
            status="trusted",
            post_type=post_type,
            archetype_id=None,
            photo=None,
            background="none",
            reason="non_calendar",
            label="",
        )

    archetype, how = select_archetype_explained(brand_id, item_id, record=cal)
    archetype_id = str(archetype.get("id") or "") if isinstance(archetype, dict) else None

    if how not in ("pinned", "rule") or not archetype_id:
        return _gap(
            post_type=post_type,
            archetype_id=archetype_id,
            reason="no_layout",
            label=f"No layout for {post_type}",
        )

    if not bool(archetype.get("vetted")):
        return _gap(
            post_type=post_type,
            archetype_id=archetype_id,
            reason="layout_not_vetted",
            label=f"No vetted layout for {post_type} ({archetype_id})",
        )

    sidecar_composed = _sidecar_for_item(item_id) or {}
    composed = sidecar_composed.get("composed")
    if isinstance(composed, dict):
        for val in composed.values():
            if isinstance(val, str) and val.strip():
                return VisualDecision(
                    status="trusted",
                    post_type=post_type,
                    archetype_id=archetype_id,
                    photo=None,
                    background="none",
                    reason="composed_present",
                    label="",
                )

    from _lib.marketing_calendar import render_mode_for_record  # noqa: PLC0415

    if render_mode_for_record(cal) == "oneshot" and not _allow_oneshot():
        return _gap(
            post_type=post_type,
            archetype_id=archetype_id,
            reason="oneshot_generated",
            label="Generated poster — needs a layout",
        )

    from _lib.template_recipe import load_recipe_for_archetype  # noqa: PLC0415

    recipe = load_recipe_for_archetype(brand_id, archetype)
    gen_slots = recipe.get("gen_slots") if isinstance(recipe, dict) else None
    has_gen = isinstance(gen_slots, list) and bool(gen_slots)
    if has_gen and not bool(cal.get("allow_generated_background")):
        tmpl = _archetype_short_label(archetype)
        return _gap(
            post_type=post_type,
            archetype_id=archetype_id,
            reason="generated_background_not_allowed",
            label=f"Needs a real photo (background would be generated)",
            background="generated_background",
        )

    applies = archetype.get("applies_to") if isinstance(archetype.get("applies_to"), dict) else {}
    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    needs_photo = bool(applies.get("needs_photo", True))
    photo_full_bleed = bg.get("kind") == "photo_full_bleed"

    if has_gen and bool(cal.get("allow_generated_background")):
        return VisualDecision(
            status="trusted",
            post_type=post_type,
            archetype_id=archetype_id,
            photo=None,
            background="generated_background",
            reason="ok",
            label="",
        )

    if not needs_photo and not photo_full_bleed:
        return VisualDecision(
            status="trusted",
            post_type=post_type,
            archetype_id=archetype_id,
            photo=None,
            background="none",
            reason="ok",
            label="",
        )

    sidecar = _sidecar_for_item(item_id) or {}
    photo = _photo_from_render_spec(cal) or _photo_from_sidecar(sidecar) or _photo_from_library(brand_id, archetype)
    if photo is None:
        tmpl = _archetype_short_label(archetype)
        return _gap(
            post_type=post_type,
            archetype_id=archetype_id,
            reason="no_real_photo",
            label=f"No real photo for {tmpl}",
            background="real_photo",
        )

    return VisualDecision(
        status="trusted",
        post_type=post_type,
        archetype_id=archetype_id,
        photo=photo,
        background="real_photo",
        reason="ok",
        label="",
    )


def sync_visual_gap_sidecar(brand_id: str, item_id: str, decision: VisualDecision) -> None:
    """Write or clear visual_gap on the caption draft sidecar."""
    from _lib.jobs.layer1._io import atomic_write  # noqa: PLC0415
    from _lib.jobs.layer5.draft_assets import _find_caption_draft_for_item  # noqa: PLC0415

    asset_id, _ = _find_caption_draft_for_item(item_id)
    if not asset_id:
        return
    path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    sidecar: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                sidecar = loaded
        except (OSError, json.JSONDecodeError):
            sidecar = {}
    if decision.is_gap():
        sidecar["visual_gap"] = {
            **decision.as_gap_payload(),
            "checked_at": _utc_now_iso(),
        }
    else:
        sidecar.pop("visual_gap", None)
    atomic_write(f"draft-assets/{asset_id}.json", sidecar)


def park_image_queue_rows(
    rows: list[dict[str, Any]],
    *,
    item_id: str,
    decision: VisualDecision,
) -> int:
    """Mark pending image pipeline rows as gap (idempotent)."""
    if not decision.is_gap():
        return 0
    parked = 0
    pref = f"inbox/{item_id}"
    for row in rows:
        if str(row.get("payload_ref") or "") != pref:
            continue
        action = str(row.get("action") or "")
        if action == "draft_image":
            action = "draft_photo"
        if action not in _IMAGE_QUEUE_ACTIONS:
            continue
        if str(row.get("status") or "").lower() != "pending":
            continue
        row["status"] = "gap"
        row["note"] = decision.label[:240]
        parked += 1
    return parked


def record_gap_for_moment(
    brand_id: str,
    item_id: str,
    decision: VisualDecision,
    *,
    rows: list[dict[str, Any]] | None = None,
) -> None:
    if not decision.is_gap():
        return
    sync_visual_gap_sidecar(brand_id, item_id, decision)
    if rows is not None:
        park_image_queue_rows(rows, item_id=item_id, decision=decision)


def clear_gap_if_trusted(brand_id: str, item_id: str, decision: VisualDecision) -> None:
    if decision.is_gap():
        return
    sync_visual_gap_sidecar(brand_id, item_id, decision)


def decision_for_api(decision: VisualDecision) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": decision.status,
        "reason": decision.reason,
        "label": decision.label,
        "post_type": decision.post_type,
        "archetype_id": decision.archetype_id,
        "background": decision.background,
    }
    if decision.photo:
        out["photo"] = {"kind": decision.photo.kind, "path": decision.photo.path}
    return out


def assert_vetted_archetypes_doc(brand_id: str) -> None:
    """Raise if any vetted archetype lacks template_pack + golden/."""
    doc = load_archetypes_doc(brand_id)
    for row in doc.get("archetypes") or []:
        if not isinstance(row, dict) or not row.get("vetted"):
            continue
        aid = str(row.get("id") or "")
        pack = str(row.get("template_pack") or "").strip()
        if not pack or not _golden_nonempty(brand_id, pack):
            raise ValueError(f"vetted archetype {aid} missing template_pack golden/")
