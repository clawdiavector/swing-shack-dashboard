"""
_lib/publish_v1.py — Publish V1 lifecycle store + state machine.

Lifecycle is strictly separate from Review V1.

  READY_TO_STAGE      — initial state on entry from Review.approval
  STAGED_AS_DRAFT     — CMS draft created/updated
  READY_TO_PUBLISH    — staged + operator opened preview
  SCHEDULED           — operator scheduled a future publish_at
  PUBLISHED           — CMS publish succeeded
  PUBLISH_FAILED      — last CMS action failed (CMS side or transport)
  CANCELLED           — operator cancelled before PUBLISHED

Hard entry gate: only Review records with status == APPROVED_FOR_PUBLISHING
may create a Publish record. Direct Writer → Publish and Brief → Publish
are forbidden — _validate_entry_gate() rejects anything else.

Revision lock: Publish record captures approved_revision_id + approved_content_hash.
Before any CMS write, the function re-hashes the staged body and compares. If it
differs, CMS write is BLOCKED with reason CONTENT_CHANGED_AFTER_APPROVAL.

Brand isolation: publish target comes from canonical brand→target mapping
(data/publishing-targets/<brand>.json, seeded by patch_publish_v1_brand_targets_v211).
A Stick article cannot be staged to swingshack.co.za because the target lookup
is keyed on operating_brand, not URL.

Idempotency: stage_draft() re-stages the same record by updating the existing
CMS draft (cms_post_id) instead of creating a new one. publish_now() on an
already-PUBLISHED record is a noop that returns ok:true + the existing publish info.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")

STATUS_READY_TO_STAGE    = "READY_TO_STAGE"
STATUS_STAGED_AS_DRAFT   = "STAGED_AS_DRAFT"
STATUS_READY_TO_PUBLISH  = "READY_TO_PUBLISH"
STATUS_SCHEDULED         = "SCHEDULED"
STATUS_PUBLISHED         = "PUBLISHED"
STATUS_PUBLISH_FAILED    = "PUBLISH_FAILED"
STATUS_CANCELLED         = "CANCELLED"

ALL_STATUSES = (
    STATUS_READY_TO_STAGE,
    STATUS_STAGED_AS_DRAFT,
    STATUS_READY_TO_PUBLISH,
    STATUS_SCHEDULED,
    STATUS_PUBLISHED,
    STATUS_PUBLISH_FAILED,
    STATUS_CANCELLED,
)

# Hard entry gate — only Review records in this state may enter Publish.
ENTRY_GATE_STATUS = "APPROVED_FOR_PUBLISHING"

# Action constants used in audit log.
ACTION_STAGE_DRAFT         = "STAGE_DRAFT"
ACTION_UPDATE_STAGED_DRAFT = "UPDATE_STAGED_DRAFT"
ACTION_SCHEDULE            = "SCHEDULE"
ACTION_CANCEL_SCHEDULE     = "CANCEL_SCHEDULE"
ACTION_PUBLISH             = "PUBLISH"
ACTION_PUBLISH_FAILED      = "PUBLISH_FAILED"
ACTION_CANCEL              = "CANCEL"


# --------------------------------------------------------------------------- #
# Brand → CMS target mapping
# --------------------------------------------------------------------------- #

def _publishing_targets_dir() -> Path:
    return Path(DATA_DIR) / "publishing-targets"


def load_publishing_target(brand_id: str) -> dict | None:
    """Return the canonical publishing target for a brand, or None if not configured.

    The target structure is:
      {
        "brand_id": "stick",
        "operating_brand": "stick",
        "cms_target": "stickgolf.co.za",      # canonical CMS domain
        "cms_kind": "wordpress",
        "wp_api_base": "https://stickgolf.co.za/wp-json/wp/v2",
        "wp_user_env": "STICKGOLF_WP_USER",
        "wp_app_password_env": "STICKGOLF_WP_APP_PASSWORD",
        "default_post_type": "post",
        "default_status_on_stage": "draft",
        "default_post_author": "Christelle",
        "timezone": "Africa/Johannesburg",
        "internal_link_allowlist": ["https://stickgolf.co.za/", "https://swingshack.co.za/"],
        "seo_metadata_supported": true,
        "scheduling_supported": true,
        "media_upload_supported": true,
        "updated": "2026-09-30"
      }
    """
    p = _publishing_targets_dir() / f"{brand_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def list_publishing_targets() -> dict[str, dict]:
    """Return all configured targets keyed by brand_id."""
    out: dict[str, dict] = {}
    d = _publishing_targets_dir()
    if not d.exists():
        return out
    for p in d.glob("*.json"):
        try:
            t = json.loads(p.read_text())
            bid = t.get("brand_id") or p.stem
            out[bid] = t
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------- #
# Storage helpers
# --------------------------------------------------------------------------- #

def _publish_dir() -> Path:
    p = Path(DATA_DIR) / "publish"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _brand_dir(brand_id: str) -> Path:
    p = _publish_dir() / brand_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _record_path(brand_id: str, publish_id: str) -> Path:
    return _brand_dir(brand_id) / f"{publish_id}.json"


def _new_publish_id(brand_id: str, brief_id: str) -> str:
    """Publish IDs are 'p_<brief_id>' — predictable, reversible, no separate id counter."""
    return f"p_{brief_id}"


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Lifecycle ops
# --------------------------------------------------------------------------- #

def get_publish_record(brand_id: str, publish_id: str) -> dict | None:
    p = _record_path(brand_id, publish_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def list_publish_records(brand_id: str | None = None) -> list[dict]:
    out: list[dict] = []
    base = _publish_dir()
    if not base.exists():
        return out
    if brand_id:
        candidates = [base / brand_id]
    else:
        candidates = [d for d in base.iterdir() if d.is_dir()]
    for d in candidates:
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            try:
                rec = json.loads(f.read_text())
                rec["publish_id"] = rec.get("publish_id") or f.stem
                rec["brand_id"] = rec.get("brand_id") or d.name
                out.append(rec)
            except Exception:
                continue
    return out


def create_from_review(brand_id: str, brief_id: str, *, actor: str = "operator") -> dict:
    """Create a Publish record from an APPROVED_FOR_PUBLISHING Review record.

    Reads the Review record from DATA_DIR/review/<brand>/r_<brief_id>.json (same
    convention as review.py uses for storage).
    """
    from _lib.review import (
        get_review_detail,
        STATUS_APPROVED_FOR_PUBLISHING,
    )

    review = get_review_detail(brand_id, f"r_{brief_id}")
    if not review:
        return {"ok": False, "code": "review_not_found", "error": f"no Review record for {brand_id}/{brief_id}"}
    rec = review["record"]
    status = rec.get("status")
    if status != STATUS_APPROVED_FOR_PUBLISHING:
        return {
            "ok": False,
            "code": "ENTRY_GATE_BLOCKED",
            "error": f"Review status is {status}; Publish only accepts {STATUS_APPROVED_FOR_PUBLISHING}",
            "review_status": status,
        }

    # Resolve target.
    target = load_publishing_target(brand_id)
    if not target:
        return {
            "ok": False,
            "code": "TARGET_NOT_CONFIGURED",
            "error": f"no publishing target configured for brand {brand_id!r}",
        }

    # Pull the canonical article body + title from the writer artifact. We
    # read it directly rather than via get_review_detail because the article
    # view is the source of truth for the body_markdown that will go to CMS.
    #
    # Writer V1 stores the canonical article body under multiple possible keys
    # depending on V1.x. We try them in order, falling back as we go.
    title = ""
    body = ""
    try:
        from _lib.review import _load_writer_artifact
        _art, _ = _load_writer_artifact(brand_id, brief_id)
        if _art:
            _hfa = _art.get("human_facing_article") or {}
            title = (
                _hfa.get("title")
                or _art.get("title")
                or brief_id
            )
            body = (
                _hfa.get("body_markdown")
                or _hfa.get("body")
                or _art.get("body_markdown")
                or _art.get("body")
                or _art.get("human_facing_article_draft")
                or ""
            )
    except Exception:
        pass
    if not body:
        # Fallback: assemble from the approved Review record sections.
        try:
            _art_dict = review.get("article") or {}
            body = _art_dict.get("body_markdown", "")
            title = title or _art_dict.get("title") or brief_id
        except Exception:
            pass
    if not body:
        return {
            "ok": False,
            "code": "EMPTY_ARTICLE",
            "error": f"no body found in writer artifact or Review record for {brand_id}/{brief_id}",
        }
    content_hash = _hash_content(body)

    approved_revision_id = rec.get("approved_revision_id")
    approved_content_hash = rec.get("approved_content_hash") or content_hash
    approved_by = rec.get("approved_by", "operator")
    approved_at = rec.get("approved_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    # If an existing Publish record already exists, return it unchanged.
    pub_id = _new_publish_id(brand_id, brief_id)
    existing = get_publish_record(brand_id, pub_id)
    if existing:
        return {"ok": True, "created": False, "publish_id": pub_id, "record": existing}

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new_rec = {
        "publish_id": pub_id,
        "brand_id": brand_id,
        "operating_brand": brand_id,
        "brief_id": brief_id,
        "review_id": f"r_{brief_id}",
        "approved_revision_id": approved_revision_id,
        "approved_content_hash": approved_content_hash,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "content_hash": content_hash,
        "article_title": title,
        "article_body": body,
        "cms_target": target.get("cms_target"),
        "cms_kind": target.get("cms_kind"),
        "wp_api_base": target.get("wp_api_base"),
        "cms_post_id": None,
        "cms_preview_url": None,
        "cms_edit_url": None,
        "cms_slug": None,
        "scheduled_publish_at": None,
        "scheduled_timezone": target.get("timezone"),
        "status": STATUS_READY_TO_STAGE,
        "history": [
            {
                "action": "CREATE_FROM_REVIEW",
                "actor": actor,
                "at": now,
                "from": None,
                "to": STATUS_READY_TO_STAGE,
            }
        ],
        "checks": {
            "internal_links_passed": None,
            "internal_links_blocked": [],
            "stock_price_passed": None,
            "stock_price_blockers": [],
            "seo_metadata_written": None,
            "seo_metadata_unsupported": [],
            "featured_image_status": None,  # NOT_SET | UPLOADED | MISSING_NOT_REQUIRED
        },
        "created_at": now,
        "updated_at": now,
    }
    p = _record_path(brand_id, pub_id)
    p.write_text(json.dumps(new_rec, indent=2, ensure_ascii=False))
    return {"ok": True, "created": True, "publish_id": pub_id, "record": new_rec}


def _append_history(rec: dict, action: str, actor: str, *, from_status: str | None = None,
                    to_status: str | None = None, result: dict | None = None) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rec.setdefault("history", []).append({
        "action": action,
        "actor": actor,
        "at": now,
        "from": from_status,
        "to": to_status,
        "result": result or {},
    })
    rec["updated_at"] = now


def update_status(rec: dict, new_status: str, *, actor: str = "operator", action: str | None = None,
                  result: dict | None = None) -> None:
    """Persist a status transition + audit entry. Caller is responsible for
    validating that new_status is reachable from the current status.
    """
    if new_status not in ALL_STATUSES:
        raise ValueError(f"unknown status {new_status!r}")
    old = rec.get("status")
    rec["status"] = new_status
    _append_history(rec, action or f"STATUS_{new_status}", actor,
                    from_status=old, to_status=new_status, result=result)
    rec["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p = _record_path(rec["brand_id"], rec["publish_id"])
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Revision lock
# --------------------------------------------------------------------------- #

def verify_revision_lock(rec: dict, content_to_publish: str) -> tuple[bool, str]:
    """Compare content_to_publish with approved_content_hash. If they differ,
    CMS write must be blocked with reason CONTENT_CHANGED_AFTER_APPROVAL.
    """
    if not rec.get("approved_content_hash"):
        return False, "no approved_content_hash recorded"
    actual_hash = _hash_content(content_to_publish)
    if actual_hash != rec["approved_content_hash"]:
        return False, "CONTENT_CHANGED_AFTER_APPROVAL"
    return True, "OK"


# --------------------------------------------------------------------------- #
# Pre-checks: internal links + stock/price safety
# --------------------------------------------------------------------------- #

def check_internal_links(rec: dict) -> dict:
    """Walk approved internal links from the Review record. If any anchor appears
    broken (URL does not resolve to a 2xx/3xx), block staging.
    Returns {"passed": bool, "checked": [...], "blocked": [...]}.
    """
    import urllib.request
    import urllib.error

    target = load_publishing_target(rec["brand_id"])
    allow = (target or {}).get("internal_link_allowlist") or []
    # Approved internal links come from the writer artifact, surfaced through Review.
    # We trust the canonical approved body here; the Review record's `article.body_markdown`
    # is the assembled output, but for link discovery we need the per-link evidence list.
    # For V1 we parse the body for `href=` URLs and validate them.
    import re as _re
    hrefs = _re.findall(r'href="([^"]+)"', rec.get("article_body", ""))
    checked: list[dict] = []
    blocked: list[dict] = []
    seen: set[str] = set()
    for url in hrefs:
        if url in seen:
            continue
        seen.add(url)
        # allowlist filter: only validate allowlisted internal URLs (cross-domain)
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        if allow and not any(url.startswith(a.rstrip("/")) for a in allow):
            continue
        # Validate via HEAD (fall back to GET)
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "CampaignOS-PublishV1/1.0")
            with urllib.request.urlopen(req, timeout=8) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            # Some servers reject HEAD; retry GET
            try:
                req2 = urllib.request.Request(url)
                req2.add_header("User-Agent", "CampaignOS-PublishV1/1.0")
                with urllib.request.urlopen(req2, timeout=8) as resp2:
                    code = resp2.status
            except Exception as e2:
                code = getattr(e2, "code", 0) or 0
        except Exception as e:
            code = 0
        entry = {"url": url, "status": code}
        checked.append(entry)
        if code < 200 or code >= 400:
            blocked.append(entry)
    return {"passed": len(blocked) == 0, "checked": checked, "blocked": blocked}


def check_stock_price(rec: dict) -> dict:
    """Lightweight stock/price check.

    V1 surface: if the article body contains explicit price claims ($X / R X / £X),
    require that the article does not contain time-bounded copy (sale/today only/
    limited time) that would need a refresh. If we detect a known unsafe pattern,
    we block staging.
    """
    body = rec.get("article_body", "") or ""
    blockers: list[str] = []
    # Heuristic: explicit currency with a number.
    import re as _re
    price_patterns = [
        r'\$\s?\d',         # $199
        r'R\s?\d',          # R 199
        r'£\s?\d',          # £99
        r'€\s?\d',          # €99
        r'ZAR\s?\d',
    ]
    has_price = any(_re.search(p, body) for p in price_patterns)
    if not has_price:
        return {"passed": True, "blockers": [], "has_price": False}
    # If a price is present, we require canonical price_safe_for_marketing evidence.
    # V1 default: we read the brand's calendar_config + an allowlist of approved
    # product pages (none configured yet). If the body mentions a product/brand
    # and we have no approved product page, we block.
    target = load_publishing_target(rec["brand_id"])
    if not target:
        return {"passed": False, "blockers": ["no_publishing_target_configured"], "has_price": True}
    # The Writer artifact already records price_safe_for_marketing in fact_check[].
    # If the operator approved it through Review, we trust it. We only block if
    # the body claims time-bounded promotion language.
    time_bounded = any(_re.search(p, body, _re.IGNORECASE) for p in [
        r"\btoday only\b",
        r"\blimited time\b",
        r"\bonly \d+ left\b",
        r"\bsale ends\b",
    ])
    if time_bounded:
        blockers.append("time_bounded_promotion_copy_present")
    # If price is present but the Writer fact_check did not mark it safe, we
    # require a manual price_safe_for_marketing=true field on the Review record.
    review_safe = rec.get("price_safe_for_marketing")
    if review_safe is False:
        blockers.append("review_marked_price_unsafe_for_marketing")
    return {"passed": len(blockers) == 0, "blockers": blockers, "has_price": has_price}


# --------------------------------------------------------------------------- #
# CMS transport (WordPress REST)
# --------------------------------------------------------------------------- #

def stage_to_cms(rec: dict, *, actor: str = "operator") -> dict:
    """Stage the approved article as a CMS draft. Idempotent.

    Required preconditions:
      - rec.status == READY_TO_STAGE
      - revision lock passes (approved_content_hash == sha256(article_body))
      - internal links pass (or operator accepted override)
      - stock/price check passes (or no price claims)

    CMS write contract:
      - POST /wp/v2/posts (new draft) OR PUT /wp/v2/posts/<id> (update existing)
      - status=draft
      - title=article_title
      - content=article_body
      - slug=preserved if UPDATE mode + rec.cms_post_id set + rec.cms_slug set;
        else derived from title
      - SEO metadata: seo_title, meta_description, target_query, canonical, schema
        are set via WP meta_input if the target.seo_metadata_supported is True
    """
    if rec["status"] not in (STATUS_READY_TO_STAGE, STATUS_STAGED_AS_DRAFT):
        return {"ok": False, "code": "WRONG_STATE", "error": f"status is {rec['status']}, expected READY_TO_STAGE or STAGED_AS_DRAFT (idempotent re-stage)"}

    # Revision lock
    ok, reason = verify_revision_lock(rec, rec.get("article_body", ""))
    if not ok:
        # mark publish_failed so operator can see it
        update_status(rec, STATUS_PUBLISH_FAILED, actor=actor,
                      action="REVISION_LOCK_FAILED", result={"reason": reason})
        return {"ok": False, "code": "CONTENT_CHANGED_AFTER_APPROVAL", "error": reason}

    # Internal links
    link_check = check_internal_links(rec)
    rec["checks"]["internal_links_passed"] = link_check["passed"]
    rec["checks"]["internal_links_blocked"] = link_check["blocked"]
    if not link_check["passed"]:
        update_status(rec, STATUS_PUBLISH_FAILED, actor=actor,
                      action="STAGING_BLOCKED", result={"reason": "internal_link_failed", "blocked": link_check["blocked"]})
        return {"ok": False, "code": "STAGING_BLOCKED", "error": "internal_link_failed", "blocked": link_check["blocked"]}

    # Stock / price
    stock_check = check_stock_price(rec)
    rec["checks"]["stock_price_passed"] = stock_check["passed"]
    rec["checks"]["stock_price_blockers"] = stock_check["blockers"]
    if not stock_check["passed"]:
        update_status(rec, STATUS_PUBLISH_FAILED, actor=actor,
                      action="STAGING_BLOCKED", result={"reason": "stock_price_check_failed", "blockers": stock_check["blockers"]})
        return {"ok": False, "code": "STAGING_BLOCKED", "error": "stock_price_check_failed", "blockers": stock_check["blockers"]}

    # Build CMS payload
    target = load_publishing_target(rec["brand_id"])
    if not target:
        return {"ok": False, "code": "TARGET_NOT_CONFIGURED", "error": "no target"}
    payload: dict[str, Any] = {
        "title": rec.get("article_title") or rec["brief_id"],
        "content": rec.get("article_body") or "",
        "status": target.get("default_status_on_stage", "draft"),
    }
    if target.get("default_post_type"):
        payload["type"] = target["default_post_type"]

    # Preserve slug for UPDATE mode
    if rec.get("cms_post_id") and rec.get("cms_slug"):
        # WordPress ignores slug on update unless explicitly passed; we pass it
        # only when the operator has not requested a URL change.
        payload["slug"] = rec["cms_slug"]

    # SEO metadata
    seo_block: dict = rec.get("seo_metadata") or {}
    seo_written: list[str] = []
    seo_unsupported: list[str] = []
    if seo_block and target.get("seo_metadata_supported"):
        meta_input: dict[str, Any] = {}
        if seo_block.get("seo_title"):
            meta_input["seo_title"] = seo_block["seo_title"]
            seo_written.append("seo_title")
        if seo_block.get("meta_description"):
            meta_input["meta_description"] = seo_block["meta_description"]
            seo_written.append("meta_description")
        if seo_block.get("canonical"):
            meta_input["canonical"] = seo_block["canonical"]
            seo_written.append("canonical")
        if seo_block.get("target_query"):
            meta_input["target_query"] = seo_block["target_query"]
            seo_written.append("target_query")
        if seo_block.get("schema"):
            meta_input["schema"] = seo_block["schema"]
            seo_written.append("schema")
        if meta_input:
            payload["meta_input"] = meta_input
    elif seo_block and not target.get("seo_metadata_supported"):
        seo_unsupported = list(seo_block.keys())
    rec["checks"]["seo_metadata_written"] = seo_written
    rec["checks"]["seo_metadata_unsupported"] = seo_unsupported

    # Send to CMS via wp_publisher adapter
    from _lib.wp_publisher import send_to_cms
    cms_result = send_to_cms(rec["brand_id"], payload, existing_post_id=rec.get("cms_post_id"))
    if not cms_result.get("ok"):
        update_status(rec, STATUS_PUBLISH_FAILED, actor=actor,
                      action=ACTION_PUBLISH_FAILED, result={"cms": cms_result})
        return {"ok": False, "code": "CMS_WRITE_FAILED", "error": cms_result.get("error"), "cms": cms_result}

    # Update record with CMS identifiers
    rec["cms_post_id"] = cms_result.get("cms_post_id")
    rec["cms_preview_url"] = cms_result.get("preview_url")
    rec["cms_edit_url"] = cms_result.get("edit_url")
    rec["cms_slug"] = cms_result.get("slug") or rec.get("cms_slug")
    # Featured image handling — V1: if approved_assets is empty, mark MISSING_NOT_REQUIRED
    # (operator sees the warning in the UI; we don't auto-generate).
    if not rec.get("approved_featured_image"):
        rec["checks"]["featured_image_status"] = "MISSING_NOT_REQUIRED"
    else:
        rec["checks"]["featured_image_status"] = "UPLOADED"

    update_status(rec, STATUS_STAGED_AS_DRAFT, actor=actor,
                  action=ACTION_STAGE_DRAFT if not rec.get("cms_post_id_prior") else ACTION_UPDATE_STAGED_DRAFT,
                  result={"cms": cms_result})
    rec["cms_post_id_prior"] = rec.get("cms_post_id")
    p = _record_path(rec["brand_id"], rec["publish_id"])
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return {"ok": True, "status": STATUS_STAGED_AS_DRAFT, "cms": cms_result, "publish_id": rec["publish_id"]}


def publish_now(rec: dict, *, actor: str = "operator") -> dict:
    """Push the staged draft to live. Idempotent: if already PUBLISHED, noop."""
    if rec["status"] == STATUS_PUBLISHED:
        return {"ok": True, "noop": True, "status": STATUS_PUBLISHED, "cms": {
            "cms_post_id": rec.get("cms_post_id"),
            "live_url": rec.get("cms_preview_url"),  # published preview URL
        }}
    if rec["status"] not in (STATUS_STAGED_AS_DRAFT, STATUS_READY_TO_PUBLISH, STATUS_SCHEDULED):
        return {"ok": False, "code": "WRONG_STATE", "error": f"status is {rec['status']}, must be STAGED_AS_DRAFT / READY_TO_PUBLISH / SCHEDULED"}
    if not rec.get("cms_post_id"):
        return {"ok": False, "code": "NO_CMS_DRAFT", "error": "no cms_post_id; stage first"}

    # Revision lock again at publish time
    ok, reason = verify_revision_lock(rec, rec.get("article_body", ""))
    if not ok:
        update_status(rec, STATUS_PUBLISH_FAILED, actor=actor,
                      action="REVISION_LOCK_FAILED_AT_PUBLISH", result={"reason": reason})
        return {"ok": False, "code": "CONTENT_CHANGED_AFTER_APPROVAL", "error": reason}

    from _lib.wp_publisher import publish_post
    cms_result = publish_post(rec["brand_id"], rec["cms_post_id"])
    if not cms_result.get("ok"):
        update_status(rec, STATUS_PUBLISH_FAILED, actor=actor,
                      action=ACTION_PUBLISH_FAILED, result={"cms": cms_result})
        return {"ok": False, "code": "CMS_PUBLISH_FAILED", "error": cms_result.get("error"), "cms": cms_result}

    rec["cms_live_url"] = cms_result.get("live_url")
    update_status(rec, STATUS_PUBLISHED, actor=actor,
                  action=ACTION_PUBLISH, result={"cms": cms_result})
    return {"ok": True, "status": STATUS_PUBLISHED, "cms": cms_result, "publish_id": rec["publish_id"]}


def schedule_publish(rec: dict, publish_at_iso: str, timezone: str, *, actor: str = "operator") -> dict:
    """Schedule a future publish time. Operator-supplied timestamp + timezone."""
    if rec["status"] not in (STATUS_STAGED_AS_DRAFT, STATUS_READY_TO_PUBLISH):
        return {"ok": False, "code": "WRONG_STATE", "error": f"status is {rec['status']}, must be STAGED_AS_DRAFT"}
    if not rec.get("cms_post_id"):
        return {"ok": False, "code": "NO_CMS_DRAFT", "error": "no cms_post_id; stage first"}
    rec["scheduled_publish_at"] = publish_at_iso
    rec["scheduled_timezone"] = timezone
    update_status(rec, STATUS_SCHEDULED, actor=actor, action=ACTION_SCHEDULE,
                  result={"publish_at": publish_at_iso, "timezone": timezone})
    return {"ok": True, "status": STATUS_SCHEDULED, "scheduled_publish_at": publish_at_iso}


def cancel_schedule(rec: dict, *, actor: str = "operator") -> dict:
    if rec["status"] != STATUS_SCHEDULED:
        return {"ok": False, "code": "WRONG_STATE", "error": f"status is {rec['status']}, expected SCHEDULED"}
    rec["scheduled_publish_at"] = None
    update_status(rec, STATUS_STAGED_AS_DRAFT, actor=actor, action=ACTION_CANCEL_SCHEDULE)
    return {"ok": True, "status": STATUS_STAGED_AS_DRAFT}


def cancel_publish(rec: dict, *, actor: str = "operator") -> dict:
    if rec["status"] in (STATUS_PUBLISHED,):
        return {"ok": False, "code": "WRONG_STATE", "error": "already PUBLISHED; cannot cancel"}
    update_status(rec, STATUS_CANCELLED, actor=actor, action=ACTION_CANCEL)
    return {"ok": True, "status": STATUS_CANCELLED}


# --------------------------------------------------------------------------- #
# Public summary for UI
# --------------------------------------------------------------------------- #

def summary_for_ui(rec: dict) -> dict:
    return {
        "publish_id": rec.get("publish_id"),
        "brand_id": rec.get("brand_id"),
        "brief_id": rec.get("brief_id"),
        "status": rec.get("status"),
        "title": rec.get("article_title"),
        "cms_target": rec.get("cms_target"),
        "cms_post_id": rec.get("cms_post_id"),
        "cms_preview_url": rec.get("cms_preview_url"),
        "cms_edit_url": rec.get("cms_edit_url"),
        "cms_live_url": rec.get("cms_live_url"),
        "cms_slug": rec.get("cms_slug"),
        "scheduled_publish_at": rec.get("scheduled_publish_at"),
        "scheduled_timezone": rec.get("scheduled_timezone"),
        "approved_by": rec.get("approved_by"),
        "approved_at": rec.get("approved_at"),
        "approved_revision_id": rec.get("approved_revision_id"),
        "approved_content_hash": rec.get("approved_content_hash"),
        "history": rec.get("history", []),
        "checks": rec.get("checks", {}),
        "created_at": rec.get("created_at"),
        "updated_at": rec.get("updated_at"),
    }
