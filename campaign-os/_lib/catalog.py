"""Campaign catalog: a review pack kept in sync with a plan's post and story steps."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable

from _lib import campaign_plan as cp
from _lib import review_pack as rp
from _lib.jobs.brand_lanes import load_brands_registry

_INDEX_NAME = "_catalog_index.json"
_SLOT_KINDS = frozenset({"post", "story"})


class CatalogError(ValueError):
    pass


def _root() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "review-packs"


def _index_path() -> Path:
    return _root() / _INDEX_NAME


def _index_key(brand_id: str, plan_id: str) -> str:
    return f"{brand_id}:{plan_id}"


def _read_index() -> dict[str, str]:
    return json.loads(_index_path().read_text(encoding="utf-8")) if _index_path().is_file() else {}


def _write_index(data: dict[str, str]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def catalog_for_plan(brand_id: str, plan_id: str) -> str | None:
    return _read_index().get(_index_key(brand_id, plan_id))


def _brand_title(brand_id: str) -> str:
    reg = load_brands_registry()
    row = (reg.get("brands") or {}).get(brand_id) or {}
    return str(row.get("display_name") or brand_id).strip()


def _plan_live(plan: dict[str, Any]) -> None:
    if plan.get("status") in (cp.PLAN_SUPERSEDED, cp.PLAN_ARCHIVED):
        raise CatalogError("This plan was replaced; open the newer one.")


def _format_when(due: str) -> str:
    try:
        d = date.fromisoformat(str(due)[:10])
    except ValueError:
        return str(due)[:120]
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def _channels(item: dict[str, Any]) -> str:
    ch = str(item.get("channel") or "").strip()
    pt = str(item.get("post_type") or "").strip()
    if ch and pt:
        return f"{ch}, {pt}"
    return ch or pt


def _caption(plan: dict[str, Any], item: dict[str, Any]) -> str:
    cap = str(item.get("caption") or "").strip()
    if cap:
        return cap[:4000]
    cid = str(item.get("calendar_id") or "").strip()
    if not cid:
        return ""
    try:
        from _lib import marketing_calendar as mc

        row = mc._newest_row(plan["brand_id"], cid)
    except Exception:
        row = None
    if not row:
        return ""
    for key in ("caption", "body", "angle", "content"):
        bit = str(row.get(key) or "").strip()
        if bit:
            return bit[:4000]
    return ""


def _slot_raw(plan: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["item_id"],
        "title": str(item.get("title") or "")[:200],
        "kind": "single",
        "caption": _caption(plan, item),
        "channels": _channels(item)[:200],
        "when": _format_when(str(item.get("due") or "")),
        "note": str(item.get("note") or "")[:600],
        "plan_item_id": item["item_id"],
    }


def _catalog_title(plan: dict[str, Any]) -> str:
    return f"{plan.get('event_name') or 'Campaign'} — {_brand_title(plan['brand_id'])}"


def _create_catalog_pack(plan: dict[str, Any]) -> dict[str, Any]:
    pack = rp.create_empty_pack(
        _catalog_title(plan),
        extra={
            "kind": "catalog",
            "plan_id": plan["plan_id"],
            "brand_id": plan["brand_id"],
            "event_name": plan.get("event_name") or "",
            "client": _brand_title(plan["brand_id"]),
        },
    )
    idx = _read_index()
    idx[_index_key(plan["brand_id"], plan["plan_id"])] = pack["id"]
    _write_index(idx)
    return pack


def ensure_for_plan(brand_id: str, plan_id: str) -> dict[str, Any]:
    plan = cp.get_plan(brand_id, plan_id)
    if not plan:
        raise CatalogError("That plan is not there.")
    _plan_live(plan)
    pack_id = catalog_for_plan(brand_id, plan_id)
    if not pack_id or rp.get_pack(pack_id) is None:
        pack = _create_catalog_pack(plan)
        pack_id = pack["id"]
    sync(brand_id, plan_id)
    return {"pack_id": pack_id}


def _visible_ids(pack: dict[str, Any]) -> set[str]:
    return {i["id"] for i in pack.get("items") or []}


def _removed_ids(pack: dict[str, Any]) -> set[str]:
    return {r["id"] for r in pack.get("removed_items") or [] if r.get("id")}


def _same_slot(item: dict[str, Any], raw: dict[str, Any]) -> bool:
    for key in ("title", "caption", "channels", "when", "note"):
        if str(item.get(key) or "") != str(raw.get(key) or ""):
            return False
    return True


def sync(brand_id: str, plan_id: str) -> dict[str, int]:
    plan = cp.get_plan(brand_id, plan_id)
    if not plan:
        raise CatalogError("That plan is not there.")
    pack_id = catalog_for_plan(brand_id, plan_id)
    if not pack_id:
        raise CatalogError("This plan has no catalog yet.")
    pack = rp.get_pack(pack_id)
    if not pack:
        raise CatalogError("That catalog is not there.")

    added = removed = updated = 0
    for item in plan.get("items") or []:
        if item.get("kind") not in _SLOT_KINDS:
            continue
        iid = item["item_id"]
        raw = _slot_raw(plan, item)
        pack = rp.get_pack(pack_id) or pack
        visible = _visible_ids(pack)
        gone = _removed_ids(pack)

        if item.get("status") == "removed":
            if iid in visible:
                rp.remove_item(pack_id, iid)
                removed += 1
            continue

        if iid in gone:
            rp.restore_item(pack_id, iid)
            added += 1
            pack = rp.get_pack(pack_id) or pack
            visible = _visible_ids(pack)

        if iid not in visible:
            rp.add_item(pack_id, raw)
            added += 1
            continue

        cur = next(i for i in pack["items"] if i["id"] == iid)
        if not _same_slot(cur, raw):
            rp.update_item_fields(
                pack_id,
                iid,
                {k: raw[k] for k in ("title", "caption", "channels", "when", "note")},
            )
            updated += 1

    rp.patch_pack(
        pack_id,
        event_name=plan.get("event_name") or "",
        title=_catalog_title(plan),
    )
    pics = refresh_pictures(brand_id, plan_id)
    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "pictures_added": pics.get("pictures_added", 0),
        "pictures_skipped": pics.get("pictures_skipped", 0),
    }


def _draft_caption(state: dict[str, Any]) -> str:
    for key in ("caption", "body", "angle", "content"):
        bit = str(state.get(key) or "").strip()
        if bit:
            return bit[:4000]
    return ""


def _post_state_once(brand_id: str) -> Callable[[str, str], dict[str, Any] | None]:
    """post_state_for builds the brand's whole post index per call. Build it once per
    refresh instead, so a 20-slot catalog does not rebuild it 20 times."""
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415
    from _lib.unified_inbox import build_post_index, post_state  # noqa: PLC0415

    cache: dict[str, Any] = {}

    def lookup(_brand: str, calendar_id: str) -> dict[str, Any] | None:
        if "records" not in cache:
            cache["index"] = build_post_index(brand_id=brand_id)
            cache["records"] = {
                str(r.get("calendar_id") or r.get("event_key") or ""): r
                for r in canonical_records(brand_id)
            }
        rec = cache["records"].get(calendar_id)
        return post_state(rec, index=cache["index"]) if rec else None

    return lookup


def refresh_pictures(
    brand_id: str,
    plan_id: str,
    *,
    post_state: Callable[[str, str], dict[str, Any] | None] | None = None,
    load_bytes: Callable[[str, str], bytes | None] | None = None,
) -> dict[str, int]:
    """Pull composed pictures from post state into catalog slots (feed, story, Google)."""
    from _lib.feed_vertical_renders import (
        FEED_RENDER_CHANNEL,
        fit_for_channel_png,
        fit_google_4x3,
        _load_png_for_url,
    )

    if post_state is None:
        post_state = _post_state_once(brand_id)
    if load_bytes is None:
        load_bytes = _load_png_for_url

    plan = cp.get_plan(brand_id, plan_id)
    pack_id = catalog_for_plan(brand_id, plan_id)
    if not plan or not pack_id:
        return {"pictures_added": 0, "pictures_skipped": 0}

    added = skipped = 0
    for row in plan.get("items") or []:
        if row.get("kind") not in _SLOT_KINDS:
            continue
        cid = str(row.get("calendar_id") or "").strip()
        if not cid:
            continue
        st = post_state(brand_id, cid)
        if not st:
            continue
        composed = st.get("composed") or {}
        feed_url = str(composed.get(FEED_RENDER_CHANNEL) or composed.get("instagram") or "").strip()
        if not feed_url:
            continue
        raw = load_bytes(brand_id, feed_url)
        if not raw:
            continue
        content_hash = hashlib.sha256(raw).hexdigest()[:32]
        pack = rp.get_pack(pack_id)
        if not pack:
            continue
        slot = next((i for i in pack.get("items") or [] if i["id"] == row["item_id"]), None)
        if not slot:
            continue
        already = content_hash in (slot.get("picture_hashes") or [])
        if not already:
            story_url = str(composed.get("instagram_story") or "").strip()
            if story_url:
                story_raw = load_bytes(brand_id, story_url)
                if not story_raw:
                    story_raw, _ = fit_for_channel_png(raw, "instagram_story")
            else:
                story_raw, _ = fit_for_channel_png(raw, "instagram_story")
            google_raw, _ = fit_google_4x3(raw)
            out = rp.add_catalog_picture(
                pack_id,
                row["item_id"],
                raw,
                source_url=feed_url,
                content_hash=content_hash,
                story_data=story_raw,
                google_data=google_raw,
            )
            if out.get("skipped"):
                skipped += 1
            else:
                added += 1
        else:
            skipped += 1
        draft_cap = _draft_caption(st)
        if draft_cap:
            pack = rp.get_pack(pack_id) or pack
            slot = next(i for i in pack["items"] if i["id"] == row["item_id"])
            empty = not str(slot.get("caption") or "").strip()
            auto = slot.get("caption_auto", True)
            if empty or auto:
                rp.update_item_fields(pack_id, row["item_id"], {"caption": draft_cap, "caption_auto": True})
    return {"pictures_added": added, "pictures_skipped": skipped, "added": added}


def counts(pack_id: str) -> dict[str, int]:
    pack = rp.get_pack(pack_id)
    if not pack:
        return {"posts": 0, "pictures": 0, "pictures_yet": 0}
    items = pack.get("items") or []
    posts = len(items)
    pictures = sum(1 for i in items if i.get("images"))
    return {"posts": posts, "pictures": pictures, "pictures_yet": max(0, posts - pictures)}


def catalog_header(pack: dict[str, Any]) -> str:
    if pack.get("kind") != "catalog":
        return ""
    items = pack.get("items") or []
    n = len(items)
    whens = [str(i.get("when") or "").strip() for i in items if i.get("when")]
    dates = whens[0] if len(whens) == 1 else (f"{whens[0]} – {whens[-1]}" if whens else "")
    event = str(pack.get("event_name") or "").strip() or str(pack.get("title") or "").split("—")[0].strip()
    c = counts(pack["id"])
    bits = [
        f"Campaign: {event or 'this plan'}",
        f"{n} post" + ("" if n == 1 else "s"),
        f"{c['pictures']} with pictures",
    ]
    if dates:
        bits.append(dates)
    return " · ".join(bits)


def list_catalog_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rp.list_packs():
        pack = rp.get_pack(row["id"])
        if not pack or pack.get("kind") != "catalog":
            continue
        c = counts(pack["id"])
        out.append(
            {
                "id": pack["id"],
                "title": pack.get("title", ""),
                "kind": "catalog",
                "plan_id": pack.get("plan_id", ""),
                "brand": pack.get("brand_id", ""),
                "counts": c,
            }
        )
    return out
