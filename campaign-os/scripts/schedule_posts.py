#!/usr/bin/env python3
"""Turn rendered images into real posts: caption, date, state, Review queue.

render_post.py makes the picture. This makes it a *post* -- the thing that shows
up in Campaign OS with a caption and a date, in a state you can approve.

    python3 campaign-os/scripts/schedule_posts.py \
        --batch data/post-batches/week-2026-10-06.json

    # on Railway, against the volume
    DATA_DIR=/data/campaign-os python3 campaign-os/scripts/schedule_posts.py \
        --batch /app/data/post-batches/week-2026-10-06.json

## How a post is actually represented

There is no separate inbox store. `intelligence.review_inbox()` reads
campaign-data.json directly and buckets each asset by its own `approvalStatus`:

    approvalStatus == "approved"  -> Approved queue
    approvalStatus == "rejected"  -> Rejected queue
    anything else                 -> Pending review   <- where you approve it

So a post is one asset row under campaigns.<campaign_id>.assets.<asset_id>,
carrying the caption, the image URL, the platform and four independent states:

    captionStatus   draft | ready
    visualStatus    brief-written | composed
    approvalStatus  review | approved | rejected     <- the Review queue
    publishStatus   planned | released               <- whether it may go out

An agent adding a post should leave approvalStatus=review and
publishStatus=planned: the work is done, a human still releases it. Override per
post with `approval_status` / `publish_status` in the batch, or for every post
with --approval-status / --publish-status.

## Batch fields this reads

    brand, slug, archetype, channels   (as render_post.py)
    date              YYYY-MM-DD  -- the day it is for
    caption           the post copy
    approval_status   default "review"
    publish_status    default "planned"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
sys.path.insert(0, str(CAMPAIGN_OS))

VALID_APPROVAL = ("review", "approved", "rejected")
VALID_PUBLISH = ("planned", "released")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def runtime_data_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    return Path(env) if env else CAMPAIGN_OS / "data"


def pin_data_dir() -> Path:
    """Make DATA_DIR explicit before any _lib import reads it.

    marketing_calendar resolves its own storage from $DATA_DIR. With the var
    unset this script defaulted to campaign-os/data while that module picked a
    different directory, so campaign-data.json and the calendar moments landed
    in two places and the week board found no moments to join. Pin one value so
    every module agrees.
    """
    resolved = runtime_data_dir()
    os.environ["DATA_DIR"] = str(resolved)
    return resolved


def brands_registry_path() -> Path:
    return runtime_data_dir() / "brands.json"


def register_campaign_ownership(brand: str, campaign_id: str) -> str:
    """Add campaign_id to brands.json -> brands.<brand>.campaign_ids.

    review_inbox() filters brand-scoped views through this list: a campaign
    absent from it is treated as unowned and hidden, so a post can exist in
    campaign-data.json and still never appear in the Review tab. Stick owned
    zero campaigns before this, which is why nothing Stick ever showed up.
    """
    path = brands_registry_path()
    if not path.is_file():
        # intelligence._runtime_data_file falls back to the bundled copy when
        # the runtime one is absent. Writing a fresh file here would shadow it
        # and silently drop every campaign already owned, so seed from bundled.
        bundled = REPO / "data" / "brands.json"
        if not bundled.is_file():
            return f"no brands.json at {path} or {bundled} -- post hidden in brand-scoped views"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bundled.read_text())
    reg = json.loads(path.read_text())
    brands = reg.setdefault("brands", {})
    row = brands.setdefault(brand, {})
    cids = row.setdefault("campaign_ids", [])
    if not isinstance(cids, list):
        return f"brands.{brand}.campaign_ids is not a list -- left alone"
    if campaign_id in cids:
        return ""
    cids.append(campaign_id)
    path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    return ""


def campaign_data_path() -> Path:
    return runtime_data_dir() / "campaign-data.json"


def _campaign_id_for(brand: str, batch_name: str) -> str:
    return f"{brand}-{batch_name}"


def _asset_id_for(brand: str, slug: str) -> str:
    return f"{brand}-{slug}"


def _image_urls(brand: str, slug: str, channel: str) -> tuple[str, str]:
    """Where render_post --publish put the files, as the app serves them."""
    png = f"composed-{slug}-{channel}.png"
    jpg = f"composed-{slug}-{channel}-publish.jpg"
    return f"/brand-images/{brand}/{png}", f"/brand-images/{brand}/{jpg}"


def build_asset(spec: dict, batch_name: str, *, approval: str, publish: str) -> tuple[str, str, dict]:
    brand = spec["brand"]
    slug = spec["slug"]
    channel = (spec.get("channels") or ["instagram"])[0]
    campaign_id = _campaign_id_for(brand, batch_name)
    asset_id = _asset_id_for(brand, slug)
    visual_url, publish_url = _image_urls(brand, slug, channel)
    caption = spec.get("caption") or ""
    # The Review card shows `name`; a caption's first line reads far better
    # there than a slug, and reviewing is the whole point of this row.
    first_line = caption.split("\n", 1)[0].strip() or slug
    asset = {
        "assetId": asset_id,
        "campaignId": campaign_id,
        "brand": brand,
        "brand_id": brand,
        "name": first_line[:72],
        "assetType": "feed-post",
        "contentType": "feed-post",
        "platform": channel,
        "caption": caption,
        "visualUrl": visual_url,
        "publishUrl": publish_url,
        "image_url": visual_url,
        "composed": {channel: visual_url},
        "archetype": spec.get("archetype"),
        "scheduledFor": spec.get("date"),
        "captionStatus": "ready" if caption else "draft",
        "visualStatus": "composed",
        "approvalStatus": approval,
        "publishStatus": publish,
        "owner": "campaign-os",
        "qualityGateState": "pending",
        "renderMode": "deterministic-template",
        "createdAt": _now(),
        "updatedAt": _now(),
        "history": [{
            "action": "composed-and-scheduled",
            "by": "campaign-os/schedule_posts.py",
            "at": _now(),
            "note": f"rendered from {spec.get('archetype')} for {spec.get('date')}; "
                    f"awaiting human approval",
        }],
    }
    return campaign_id, asset_id, asset


def ensure_calendar_moment(spec: dict, asset_id: str) -> tuple[str, str]:
    """Create/update the calendar moment the post sits on. Returns (cal_id, note).

    "This week" is driven by marketing-calendar moments, not by asset rows --
    week_board() walks canonical_records() and joins drafts onto them. A post
    with only an asset row has no moment to sit on, so the week shows "Nothing
    going out" even though the post exists and is in Review. That is exactly
    what happened on 2026-10-05.
    """
    sys.path.insert(0, str(CAMPAIGN_OS))
    from _lib.marketing_calendar import upsert_event  # noqa: PLC0415

    brand = spec["brand"]
    date_s = spec.get("date")
    if not date_s:
        return "", "no date -- cannot place it on the calendar"
    # upsert_event enforces an event_key prefixed "<brand_id>:" -- a hyphen is
    # rejected with "does not match brand_id".
    cal_key = f"{brand}:{spec['slug']}"
    record = {
        "event_key": cal_key,
        "brand_id": brand,
        "title": (spec.get("caption") or spec["slug"]).split("\n", 1)[0].strip()[:72],
        "event_date": date_s,
        "event_start": date_s,
        "event_end": date_s,
        # Not an automation writer: V2.8 routes scout/heidi/reactive to a
        # separate intake store and blocks template/demo writers outright.
        # This is operator-equivalent work, so it belongs on the main calendar.
        # week_board only shows moments whose status is in
        # {approved, candidate, active, completed}. A record with no status is
        # silently skipped, which is why the week read "Nothing going out" while
        # the posts sat in Review. "approved" = the slot is booked; whether the
        # POST may go out is the asset's own approvalStatus/publishStatus.
        "status": "approved",
        "source_origin": "internal_strategy",
        "created_by": "campaign-os-schedule-posts",
        "post_type": spec.get("archetype") or "feed-post",
        "primary_channel": (spec.get("channels") or ["instagram"])[0],
        "render_mode": "deterministic-template",
    }
    try:
        result = upsert_event(brand, record)
    except Exception as e:  # noqa: BLE001
        return "", f"calendar upsert failed: {type(e).__name__}: {e}"
    rec = result.get("record") or {}
    cal_id = str(rec.get("calendar_id") or rec.get("event_key") or cal_key)

    # upsert_event does not accept `status` from the caller -- it stays None,
    # and week_board skips any moment whose status is not in
    # {approved, candidate, active, completed}. Transition it explicitly so the
    # slot is booked and visible in This week.
    if str(rec.get("status") or "") not in ("approved", "candidate", "active", "completed"):
        from _lib.marketing_calendar import transition_status  # noqa: PLC0415
        try:
            transition_status(brand, cal_id, "approved",
                              reason="booked by campaign-os/schedule_posts.py")
        except Exception as e:  # noqa: BLE001
            return cal_id, f"moment created but status transition failed: {e}"
    return cal_id, ""


def write_draft_sidecar(spec: dict, campaign_id: str, asset_id: str, cal_id: str,
                        *, composed: dict[str, str] | None = None,
                        created_by: str = "campaign-os/schedule_posts.py") -> None:
    """The join row week_board() indexes by calendar_id.

    _index_draft_sidecars() reads draft-assets/*.json and resolves the moment
    from source_inbox_item_id, which must be calendar_candidate:<brand>:<cal_id>.
    Without this file the post never joins its moment and the week stays empty.

    `composed` maps every rendered channel to its URL. The publish queue reads
    it per platform, so a post rendered for Instagram and Facebook needs both.
    """
    brand = spec["brand"]
    channel = (spec.get("channels") or ["instagram"])[0]
    visual_url, _ = _image_urls(brand, spec["slug"], channel)
    composed = dict(composed or {channel: visual_url})
    sidecar = {
        "asset_id": asset_id,
        "campaign_id": campaign_id,
        "brand_id": brand,
        "source_inbox_item_id": f"calendar_candidate:{brand}:{cal_id}",
        "composed": composed,
        "image_url": composed.get(channel) or visual_url,
        "created_at": _now(),
        "action": "compose_post",
        "created_by": created_by,
    }
    out = runtime_data_dir() / "draft-assets" / f"{asset_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--approval-status", choices=VALID_APPROVAL,
                    help="override every post's approval state")
    ap.add_argument("--publish-status", choices=VALID_PUBLISH,
                    help="override every post's publish state")
    ap.add_argument("--no-calendar", action="store_true",
                    help="skip the calendar moment (post will not show in This week)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pin_data_dir()
    specs = json.loads(Path(a.batch).read_text())
    batch_name = Path(a.batch).stem

    cd_path = campaign_data_path()
    if not cd_path.is_file():
        raise SystemExit(f"no campaign-data.json at {cd_path}. Is DATA_DIR right?")
    data = json.loads(cd_path.read_text())
    campaigns = data.setdefault("campaigns", {})

    written, skipped = [], []
    for spec in specs:
        approval = a.approval_status or spec.get("approval_status") or "review"
        publish = a.publish_status or spec.get("publish_status") or "planned"
        if approval not in VALID_APPROVAL or publish not in VALID_PUBLISH:
            skipped.append(f"{spec.get('slug')}: bad state {approval}/{publish}")
            continue
        if not spec.get("caption"):
            skipped.append(f"{spec.get('slug')}: no caption -- a post needs copy")
            continue
        cid, aid, asset = build_asset(spec, batch_name, approval=approval, publish=publish)
        campaign = campaigns.setdefault(cid, {
            "identity": {"name": f"{spec['brand']} — {batch_name}"},
            "brand_id": spec["brand"],
            "assets": {},
        })
        assets = campaign.setdefault("assets", {})
        # Re-running must update in place, never duplicate the post.
        existing = assets.get(aid)
        if isinstance(existing, dict):
            asset["createdAt"] = existing.get("createdAt", asset["createdAt"])
            asset["history"] = (existing.get("history") or []) + asset["history"]
        assets[aid] = asset
        if not a.dry_run:
            warn = register_campaign_ownership(spec["brand"], cid)
            if warn:
                skipped.append(f"{spec.get('slug')}: {warn}")
            if not a.no_calendar:
                cal_id, cal_warn = ensure_calendar_moment(spec, aid)
                if cal_warn:
                    skipped.append(f"{spec.get('slug')}: {cal_warn}")
                else:
                    asset["calendarId"] = cal_id
                    write_draft_sidecar(spec, cid, aid, cal_id)
        written.append((spec.get("date"), spec["brand"], aid, approval, publish))

    if not a.dry_run:
        data["updatedAt"] = _now()
        cd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    verb = "would write" if a.dry_run else "wrote"
    print(f"{verb} {len(written)} posts into {cd_path}")
    for date, brand, aid, approval, publish in sorted(written):
        print(f"  {date}  {brand:<12} {aid:<34} {approval}/{publish}")
    for s in skipped:
        print(f"  SKIPPED {s}")
    print("\nThey appear in Review (pending) because approvalStatus is not "
          "'approved' or 'rejected'. Approving there is a human action.")
    return 1 if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
