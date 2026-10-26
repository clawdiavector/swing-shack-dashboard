"""Archive drafts, plans, and calendar suggestions; restore; purge after retention.

Archived items stay in DATA_DIR until a daily job purges them past retention
(default 30 days). Every archive, restore, and purge is appended to an audit log.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger("campaign_os.content_archive")

from _lib.archive_retention import purge_at_iso, retention_days
from _lib.brand_validate import validate_brand_id

KINDS = frozenset({"draft", "plan", "suggestion"})


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", "data")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except ValueError:
        return None


def _audit_path() -> str:
    return os.path.join(_data_dir(), "archive", "content-audit.jsonl")


def append_audit(
    *,
    action: str,
    kind: str,
    item_id: str,
    brand_id: str,
    actor: str,
    title: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    row = {
        "at": _now_iso(),
        "action": action,
        "kind": kind,
        "item_id": item_id,
        "brand_id": brand_id,
        "actor": actor,
        "title": title,
    }
    if extra:
        row.update(extra)
    path = _audit_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_audit(*, brand_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    path = _audit_path()
    if not os.path.isfile(path):
        return []
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if brand_id and row.get("brand_id") != brand_id:
                    continue
                rows.append(row)
    except OSError:
        return []
    return rows[-limit:]


def _item_row(
    *,
    kind: str,
    item_id: str,
    title: str,
    archived_at: str,
    archived_by: str,
    touches: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": kind,
        "id": item_id,
        "title": title,
        "archived_at": archived_at,
        "archived_by": archived_by,
        "purge_at": purge_at_iso(archived_at),
        "touches": touches or [],
    }
    if extra:
        row.update(extra)
    return row


def list_archived(brand_id: str) -> list[dict[str, Any]]:
    bid = validate_brand_id(brand_id, allow_sentinel=False)
    out: list[dict[str, Any]] = []
    out.extend(_archived_drafts(bid))
    out.extend(_archived_plans(bid))
    out.extend(_archived_suggestions(bid))
    out.sort(key=lambda r: (r.get("archived_at") or "", r.get("title") or ""), reverse=True)
    return out


def _archived_drafts(brand_id: str) -> list[dict[str, Any]]:
    from _lib.library_shelf import _build_draft_rows  # noqa: PLC0415
    from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

    data = _load_campaign_data()
    rows: list[dict[str, Any]] = []
    for r in _build_draft_rows(brand_id):
        if str(r.get("status") or "") != "archived":
            continue
        aid = str(r.get("asset_id") or "")
        asset = None
        cid = str(r.get("campaign_id") or "")
        camp = (data.get("campaigns") or {}).get(cid) or {}
        asset = (camp.get("assets") or {}).get(aid) or {}
        archived_at = str(asset.get("archived_at") or r.get("updated_at") or "")
        archived_by = str(asset.get("archived_by") or "operator")
        title = str(r.get("title") or aid)
        touches: list[str] = []
        if str(r.get("publish_state") or "") in ("scheduled", "postiz_scheduled"):
            touches.append("also removes it from Postiz when archived from the publish queue")
        rows.append(
            _item_row(
                kind="draft",
                item_id=aid,
                title=title,
                archived_at=archived_at or _now_iso(),
                archived_by=archived_by,
                touches=touches,
                extra={"campaign_id": cid},
            )
        )
    return rows


def _archived_plans(brand_id: str) -> list[dict[str, Any]]:
    from _lib import campaign_plan as cp  # noqa: PLC0415

    rows: list[dict[str, Any]] = []
    for p in cp.list_plans(brand_id, status=cp.PLAN_ARCHIVED):
        pid = str(p.get("plan_id") or "")
        rows.append(
            _item_row(
                kind="plan",
                item_id=pid,
                title=str(p.get("event_name") or p.get("brief_id") or pid),
                archived_at=str(p.get("archived_at") or p.get("updated_at") or ""),
                archived_by=str(p.get("archived_by") or "operator"),
                touches=["plan steps leave Todo and calendar alerts until restored"],
            )
        )
    return rows


def _archived_suggestions(brand_id: str) -> list[dict[str, Any]]:
    from _lib import calendar_suggestions as cs  # noqa: PLC0415
    from _lib import marketing_calendar as mc  # noqa: PLC0415

    rows: list[dict[str, Any]] = []
    for r in mc.latest_revisions(mc.list_records(brand_id) or []):
        if r.get("status") != "archived":
            continue
        cid = str(r.get("calendar_id") or r.get("event_key") or "")
        title = str(r.get("title") or r.get("name") or cid)
        rows.append(
            _item_row(
                kind="suggestion",
                item_id=cid,
                title=title,
                archived_at=str(r.get("archived_at") or r.get("last_verified") or ""),
                archived_by=str(r.get("archived_by") or "operator"),
                touches=["hidden from the faded calendar suggestions grid"],
                extra={"suggestion_source": "row", "suggestion_key": cs.row_key(cid)},
            )
        )

    for key, dec in cs.read_decisions(brand_id).items():
        if dec.get("decision") != "archived":
            continue
        rows.append(
            _item_row(
                kind="suggestion",
                item_id=key,
                title=str(dec.get("title") or key),
                archived_at=str(dec.get("at") or ""),
                archived_by=str(dec.get("actor") or "operator"),
                touches=["hidden from the faded calendar suggestions grid"],
                extra={"suggestion_source": "decision", "suggestion_key": key},
            )
        )
    return rows


def preview_archive(
    brand_id: str,
    *,
    kind: str,
    item_id: str,
    suggestion_key: str | None = None,
    title_hint: str | None = None,
) -> dict[str, Any]:
    kind_norm = str(kind or "").strip().lower()
    if kind_norm not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    bid = validate_brand_id(brand_id, allow_sentinel=False)
    iid = str(item_id or "").strip()
    if not iid:
        raise ValueError("item id required")
    title, touches = _resolve_title_touches(bid, kind_norm, iid, suggestion_key, title_hint)
    purge = purge_at_iso(_now_iso())
    msg = f'Archive "{title}"?'
    if touches:
        msg += " " + " ".join(touches)
    msg += f" Permanently removed after {purge[:10]} unless restored."
    return {"ok": True, "kind": kind_norm, "id": iid, "title": title, "message": msg, "touches": touches, "purge_at": purge}


def _resolve_title_touches(
    brand_id: str,
    kind: str,
    item_id: str,
    suggestion_key: str | None,
    title_hint: str | None,
) -> tuple[str, list[str]]:
    if kind == "draft":
        from _lib.library_shelf import _build_draft_rows  # noqa: PLC0415

        for r in _build_draft_rows(brand_id):
            if str(r.get("asset_id") or "") == item_id:
                title = str(r.get("title") or item_id)
                touches = []
                if str(r.get("publish_state") or "") in ("scheduled", "postiz_scheduled"):
                    touches.append("Also removes it from Postiz.")
                return title, touches
        raise ValueError("draft not found")
    if kind == "plan":
        from _lib import campaign_plan as cp  # noqa: PLC0415

        plan = cp.get_plan(brand_id, item_id)
        if not plan:
            raise ValueError("plan not found")
        if plan.get("status") == cp.PLAN_ARCHIVED:
            raise ValueError("plan is already archived")
        return str(plan.get("event_name") or plan.get("brief_id") or item_id), [
            "Plan steps leave Todo until restored."
        ]
    if kind == "suggestion":
        key = (suggestion_key or item_id).strip()
        if key.startswith("row:"):
            from _lib import marketing_calendar as mc  # noqa: PLC0415

            cid = key.split(":", 1)[1]
            row = mc._newest_row(brand_id, cid)  # noqa: SLF001
            if not row:
                raise ValueError("suggestion not found")
            return str(row.get("title") or row.get("name") or cid), [
                "Hidden from the calendar suggestion grid."
            ]
        title = title_hint or key
        return title, ["Hidden from the calendar suggestion grid."]
    return item_id, []


def archive_item(
    brand_id: str,
    *,
    kind: str,
    item_id: str,
    actor: str,
    suggestion_key: str | None = None,
    title_hint: str | None = None,
) -> dict[str, Any]:
    kind_norm = str(kind or "").strip().lower()
    preview = preview_archive(
        brand_id,
        kind=kind_norm,
        item_id=item_id,
        suggestion_key=suggestion_key,
        title_hint=title_hint,
    )
    bid = validate_brand_id(brand_id, allow_sentinel=False)
    iid = str(item_id or "").strip()
    at = _now_iso()
    purge = purge_at_iso(at)

    if kind_norm == "draft":
        from _lib.library_shelf import _archive_draft, _build_draft_rows  # noqa: PLC0415
        from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

        row = next((r for r in _build_draft_rows(bid) if str(r.get("asset_id")) == iid), None)
        if not row:
            raise ValueError("draft not found")
        cid = str(row.get("campaign_id") or "")
        if not _archive_draft(iid, cid):
            raise ValueError("draft not found")
        data = _load_campaign_data()
        asset = ((data.get("campaigns") or {}).get(cid) or {}).get("assets", {}).get(iid) or {}
        if isinstance(asset, dict):
            asset["archived_at"] = at
            asset["archived_by"] = actor
            asset["purge_at"] = purge
            asset["status_before_archive"] = asset.get("approvalStatus")
            _write_campaign_data(data)
    elif kind_norm == "plan":
        from _lib import campaign_plan as cp  # noqa: PLC0415

        r = cp.archive_plan(bid, iid, actor)
        if not r.get("ok"):
            raise ValueError(r.get("error") or "archive failed")
    elif kind_norm == "suggestion":
        key = (suggestion_key or iid).strip()
        if key.startswith("row:"):
            from _lib import marketing_calendar as mc  # noqa: PLC0415

            cid = key.split(":", 1)[1]
            prev = mc._newest_row(bid, cid)  # noqa: SLF001
            if not prev or prev.get("status") == "archived":
                raise ValueError("suggestion not found")
            updated = mc.transition_status(bid, cid, "archived", reason=f"archived by {actor}")
            if not updated:
                raise ValueError("suggestion not found")
            mc.append_fields(bid, cid, {"archived_at": at, "archived_by": actor, "purge_at": purge,
                                          "status_before_archive": prev.get("status")})
        else:
            from _lib import calendar_suggestions as cs  # noqa: PLC0415

            cs.record_decision(
                bid,
                key,
                "archived",
                actor,
                title=title_hint or key,
                purge_at=purge,
            )
    else:
        raise ValueError(f"unknown kind {kind_norm}")

    append_audit(
        action="archive",
        kind=kind_norm,
        item_id=iid,
        brand_id=bid,
        actor=actor,
        title=preview["title"],
        extra={"purge_at": purge, "suggestion_key": suggestion_key},
    )
    return {"ok": True, "kind": kind_norm, "id": iid, "archived_at": at, "purge_at": purge}


def restore_item(
    brand_id: str,
    *,
    kind: str,
    item_id: str,
    actor: str,
    suggestion_key: str | None = None,
) -> dict[str, Any]:
    kind_norm = str(kind or "").strip().lower()
    if kind_norm not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    bid = validate_brand_id(brand_id, allow_sentinel=False)
    iid = str(item_id or "").strip()
    title = iid

    if kind_norm == "draft":
        from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

        data = _load_campaign_data()
        found = False
        for camp in (data.get("campaigns") or {}).values():
            assets = camp.get("assets") or {}
            if iid not in assets:
                continue
            asset = assets[iid]
            if str(asset.get("approvalStatus") or "") != "archived":
                raise ValueError("draft is not archived")
            title = str(asset.get("caption") or asset.get("title") or iid)[:80]
            prev = asset.get("status_before_archive") or "pending"
            asset["approvalStatus"] = prev if prev != "archived" else "pending"
            for k in ("archived_at", "archived_by", "purge_at", "status_before_archive"):
                asset.pop(k, None)
            asset["updatedAt"] = _now_iso()
            found = True
            break
        if not found:
            raise ValueError("draft not found")
        _write_campaign_data(data)
    elif kind_norm == "plan":
        from _lib import campaign_plan as cp  # noqa: PLC0415

        r = cp.restore_plan(bid, iid, actor)
        if not r.get("ok"):
            raise ValueError(r.get("error") or "restore failed")
        plan = cp.get_plan(bid, iid) or {}
        title = str(plan.get("event_name") or iid)
    elif kind_norm == "suggestion":
        key = (suggestion_key or iid).strip()
        if key.startswith("row:"):
            from _lib import marketing_calendar as mc  # noqa: PLC0415

            cid = key.split(":", 1)[1]
            row = mc._newest_row(bid, cid)  # noqa: SLF001
            if not row or row.get("status") != "archived":
                raise ValueError("suggestion is not archived")
            title = str(row.get("title") or cid)
            prev = row.get("status_before_archive") or "candidate"
            mc.transition_status(bid, cid, prev, reason=f"restored by {actor}")
            mc.append_fields(bid, cid, {}, clear=("archived_at", "archived_by", "purge_at", "status_before_archive"))
        else:
            from _lib import calendar_suggestions as cs  # noqa: PLC0415

            dec = cs.read_decisions(bid).get(key)
            if not dec or dec.get("decision") != "archived":
                raise ValueError("suggestion is not archived")
            title = str(dec.get("title") or key)
            cs.clear_decision(bid, key)
    else:
        raise ValueError(f"unknown kind {kind_norm}")

    append_audit(
        action="restore",
        kind=kind_norm,
        item_id=iid,
        brand_id=bid,
        actor=actor,
        title=title,
        extra={"suggestion_key": suggestion_key},
    )
    return {"ok": True, "kind": kind_norm, "id": iid}


def _is_past_purge(purge_at: str, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    pt = _parse_iso(purge_at)
    if not pt:
        return False
    return pt <= now


def _meta_post_link(asset_id: str) -> dict[str, Any] | None:
    from _lib.post_links import INDEX_NAME, _load_index  # noqa: PLC0415

    path = Path(_data_dir()) / INDEX_NAME
    if not path.is_file():
        return None
    idx = _load_index(path)
    link = (idx.get("by_asset_id") or {}).get(asset_id)
    return link if isinstance(link, dict) else None


def _published_items_has_asset(asset_id: str) -> bool:
    path = Path(_data_dir()) / "published-items.json"
    if not path.is_file():
        return False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    rows = doc.get("published") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return False
    for it in rows:
        if not isinstance(it, dict):
            continue
        for key in ("asset_id", "assetId", "id", "item_id", "publish_id", "publishId"):
            if str(it.get(key) or "") == asset_id:
                return True
    return False


def draft_is_published(asset_id: str) -> bool:
    """True when this draft asset has already shipped (must never be purged)."""
    link = _meta_post_link(asset_id)
    if link and link.get("published_at"):
        return True
    if _published_items_has_asset(asset_id):
        return True
    from _lib.unified_inbox import _campaign_asset_for_id, _load_campaign_data  # noqa: PLC0415

    _cid, asset = _campaign_asset_for_id(_load_campaign_data(), asset_id)
    if isinstance(asset, dict):
        status = str(asset.get("approvalStatus") or asset.get("publishStatus") or "").lower()
        if status == "published":
            return True
    return False


def _postiz_post_id_for_archived_draft(brand_id: str, asset_id: str) -> str:
    link = _meta_post_link(asset_id)
    if link:
        pid = str(link.get("postiz_post_id") or "").strip()
        if pid:
            return pid
    from _lib import publish_sandbox as sandbox  # noqa: PLC0415
    from _lib.unified_inbox import asset_id_from_queue_row  # noqa: PLC0415

    for rec in sandbox._read_jsonl(sandbox._receipts_path()):  # noqa: SLF001
        if str(rec.get("brand_id") or "") != brand_id:
            continue
        aid = asset_id_from_queue_row(rec)
        if aid != asset_id:
            continue
        pid = str(rec.get("postiz_post_id") or "").strip()
        if pid:
            return pid
    return ""


def _delete_postiz_on_purge(brand_id: str, asset_id: str) -> None:
    postiz_id = _postiz_post_id_for_archived_draft(brand_id, asset_id)
    if not postiz_id:
        return
    from _lib.postiz_client import delete_post  # noqa: PLC0415

    _data, err = delete_post(postiz_id)
    if err:
        code = err[0] if err else "error"
        msg = err[1] if len(err) > 1 and err[1] else ""
        raise ValueError(f"postiz delete_post failed: {code} {msg}"[:200])


def _skip_purge_published_draft(
    brand_id: str,
    asset_id: str,
    actor: str,
    *,
    title: str = "",
) -> None:
    _LOG.info("purge skipped published draft brand=%s asset=%s", brand_id, asset_id)
    append_audit(
        action="purge_skipped",
        kind="draft",
        item_id=asset_id,
        brand_id=brand_id,
        actor=actor,
        title=title,
        extra={"reason": "published"},
    )


def purge_expired(*, now: datetime | None = None, actor: str = "job:archive_purge") -> dict[str, Any]:
    """Delete items archived past retention. Returns counts per kind."""
    now = now or datetime.now(timezone.utc)
    counts: dict[str, int] = {"draft": 0, "plan": 0, "suggestion": 0, "skipped_published": 0}
    brands = ("swing-shack", "stick", "bag-drop")
    for bid in brands:
        for item in list_archived(bid):
            if not _is_past_purge(str(item.get("purge_at") or ""), now=now):
                continue
            kind = item.get("kind")
            iid = str(item.get("id") or "")
            try:
                if kind == "draft":
                    if draft_is_published(iid):
                        _skip_purge_published_draft(
                            bid,
                            iid,
                            actor,
                            title=str(item.get("title") or ""),
                        )
                        counts["skipped_published"] += 1
                        continue
                    _purge_draft(bid, iid, str(item.get("campaign_id") or ""), actor)
                    counts["draft"] += 1
                elif kind == "plan":
                    _purge_plan(bid, iid, actor)
                    counts["plan"] += 1
                elif kind == "suggestion":
                    _purge_suggestion(bid, item, actor)
                    counts["suggestion"] += 1
            except (ValueError, OSError):
                continue
    total = counts["draft"] + counts["plan"] + counts["suggestion"]
    return {"ok": True, "purged": counts, "total": total}


def _purge_draft(brand_id: str, asset_id: str, campaign_id: str, actor: str) -> None:
    from _lib.library_shelf import _delete_draft  # noqa: PLC0415

    _delete_postiz_on_purge(brand_id, asset_id)
    _delete_draft(asset_id, campaign_id)
    append_audit(action="purge", kind="draft", item_id=asset_id, brand_id=brand_id, actor=actor)


def _purge_plan(brand_id: str, plan_id: str, actor: str) -> None:
    from _lib import campaign_plan as cp  # noqa: PLC0415

    cp.purge_plan(brand_id, plan_id, actor)
    append_audit(action="purge", kind="plan", item_id=plan_id, brand_id=brand_id, actor=actor)


def _purge_suggestion(brand_id: str, item: dict[str, Any], actor: str) -> None:
    from _lib import calendar_suggestions as cs  # noqa: PLC0415
    from _lib import marketing_calendar as mc  # noqa: PLC0415

    extra = item.get("suggestion_source")
    iid = str(item.get("id") or "")
    if extra == "decision":
        cs.clear_decision(brand_id, iid)
    else:
        cid = iid
        mc.transition_status(brand_id, cid, "purged", reason=f"purged by {actor}")
    append_audit(
        action="purge",
        kind="suggestion",
        item_id=iid,
        brand_id=brand_id,
        actor=actor,
        title=str(item.get("title") or ""),
    )
