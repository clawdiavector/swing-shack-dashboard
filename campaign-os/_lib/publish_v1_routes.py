"""
_lib/publish_v1_routes.py — Flask Blueprint for Publish V1.

Routes (session-auth only):
  GET    /api/publish/v1/targets                       — list all configured targets
  GET    /api/publish/v1/targets/<brand>               — one target (with probe)
  POST   /api/publish/v1/from-review/<brand>/<brief>   — create a Publish record
                                                          from an APPROVED_FOR_PUBLISHING
                                                          Review record (entry gate)
  GET    /api/publish/v1/queue                         — list Publish records
  GET    /api/publish/v1/queue/<brand>                 — per-brand queue
  GET    /api/publish/v1/<brand>/<publish_id>          — detail + history + checks
  POST   /api/publish/v1/<brand>/<publish_id>/stage    — send to CMS as draft
  POST   /api/publish/v1/<brand>/<publish_id>/publish  — publish now (human action)
  POST   /api/publish/v1/<brand>/<publish_id>/schedule — schedule future publish
  POST   /api/publish/v1/<brand>/<publish_id>/cancel-schedule — cancel schedule
  POST   /api/publish/v1/<brand>/<publish_id>/cancel    — cancel the publish job

The route keys never come from caller-controlled URL params. Brand id comes
from the path but is validated against the brand registry; the target config
is loaded by operating_brand, not by user-supplied URL. A Stick article cannot
be staged to swingshack.co.za because the cms_target is read from the brand's
own publishing-targets/<brand>.json file.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")


def register_routes(app):
    bp = Blueprint("publish_v1", __name__)

    def _is_authed_session(req):
        """Session auth — same pattern as Review V1 routes.

        Mirrors app._is_authed():
          - cos_session cookie signed via itsdangerous URLSafeTimedSerializer
          - bearer token fallback for programmatic access
        """
        try:
            from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
            secret = (
                os.environ.get("CAMPAIGN_OS_SECRET")
                or os.environ.get("SESSION_SECRET")
                or os.environ.get("CAMPAIGN_OS_PASSWORD")
                or "dev-secret"
            )
            s = URLSafeTimedSerializer(secret)
            token = req.cookies.get("cos_session")
            if token:
                try:
                    s.loads(token, max_age=60 * 60 * 24 * 30)
                    return True
                except (BadSignature, SignatureExpired):
                    return False
            auth = req.headers.get("Authorization", "")
            if auth.lower().startswith("bearer ") and len(auth.split(" ", 1)[1].strip()) > 0:
                return True
        except Exception:
            pass
        return False

    def _auth_gate():
        if not _is_authed_session(request):
            return jsonify({"ok": False, "error": "authentication required"}), 401
        return None

    @bp.route("/api/publish/v1/targets", methods=["GET"])
    def list_targets():
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.publish_v1 import list_publishing_targets
        targets = list_publishing_targets()
        # Strip internal env-var names from response (operator should not see which env vars map).
        safe = {
            bid: {
                "brand_id": t.get("brand_id"),
                "operating_brand": t.get("operating_brand"),
                "cms_target": t.get("cms_target"),
                "cms_kind": t.get("cms_kind"),
                "default_post_type": t.get("default_post_type"),
                "default_status_on_stage": t.get("default_status_on_stage"),
                "timezone": t.get("timezone"),
                "seo_metadata_supported": t.get("seo_metadata_supported"),
                "scheduling_supported": t.get("scheduling_supported"),
                "media_upload_supported": t.get("media_upload_supported"),
                "enabled": t.get("enabled"),
            }
            for bid, t in targets.items()
        }
        return jsonify({"ok": True, "targets": safe, "count": len(safe)}), 200

    @bp.route("/api/publish/v1/targets/<brand_id>", methods=["GET"])
    def get_target(brand_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.publish_v1 import load_publishing_target
        from _lib.wp_publisher import test_target
        t = load_publishing_target(brand_id)
        if not t:
            return jsonify({"ok": False, "error": f"no target for {brand_id!r}"}), 404
        probe = test_target(brand_id) if t.get("enabled") else {"ok": False, "code": "TARGET_DISABLED", "note": "target.enabled is false (no creds)"}
        return jsonify({"ok": True, "target": t, "probe": probe}), 200

    @bp.route("/api/publish/v1/from-review/<brand_id>/<brief_id>", methods=["POST"])
    def from_review(brand_id, brief_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import create_from_review
        result = create_from_review(brand_id, brief_id)
        status = 200 if result.get("ok") else 403 if result.get("code") == "ENTRY_GATE_BLOCKED" else 400
        return jsonify(result), status

    @bp.route("/api/publish/v1/queue", methods=["GET"])
    def queue_all():
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.publish_v1 import list_publish_records, summary_for_ui
        return jsonify({
            "ok": True,
            "queue": [summary_for_ui(r) for r in list_publish_records()],
            "count": len(list_publish_records()),
        }), 200

    @bp.route("/api/publish/v1/queue/<brand_id>", methods=["GET"])
    def queue_brand(brand_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import list_publish_records, summary_for_ui
        recs = [r for r in list_publish_records(brand_id) if r.get("brand_id") == brand_id]
        return jsonify({
            "ok": True,
            "queue": [summary_for_ui(r) for r in recs],
            "count": len(recs),
        }), 200

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>", methods=["GET"])
    def get_record(brand_id, publish_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import get_publish_record, summary_for_ui
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        return jsonify({"ok": True, "record": summary_for_ui(rec)}), 200

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>/stage", methods=["POST"])
    def stage(brand_id, publish_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import get_publish_record, stage_to_cms
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        result = stage_to_cms(rec)
        status = 200 if result.get("ok") else 403 if result.get("code") == "CONTENT_CHANGED_AFTER_APPROVAL" else 502
        return jsonify(result), status

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>/publish", methods=["POST"])
    def publish(brand_id, publish_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import get_publish_record, publish_now
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        result = publish_now(rec)
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>/schedule", methods=["POST"])
    def schedule(brand_id, publish_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        body = request.get_json(silent=True) or {}
        publish_at = (body.get("publish_at") or "").strip()
        tz = (body.get("timezone") or "").strip()
        if not publish_at or not tz:
            return jsonify({"ok": False, "error": "publish_at (ISO) and timezone required"}), 400
        from _lib.publish_v1 import get_publish_record, schedule_publish
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        result = schedule_publish(rec, publish_at, tz)
        return jsonify(result), 200 if result.get("ok") else 400

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>/cancel-schedule", methods=["POST"])
    def cancel_schedule(brand_id, publish_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import get_publish_record, cancel_schedule
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        result = cancel_schedule(rec)
        return jsonify(result), 200 if result.get("ok") else 400

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>/cancel", methods=["POST"])
    def cancel(brand_id, publish_id):
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        from _lib.publish_v1 import get_publish_record, cancel_publish
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        result = cancel_publish(rec)
        return jsonify(result), 200 if result.get("ok") else 400

    @bp.route("/api/publish/v1/<brand_id>/<publish_id>/attach-media", methods=["POST"])
    def attach_media(brand_id, publish_id):
        """Attach an existing CMS media id as the publish record's featured image.

        Body: {"media_id": 3756} — must be a real WP media id. The media must
        already exist in the CMS (uploads happen out-of-band via the standard
        WP /wp/v2/media endpoint).
        """
        gate = _auth_gate()
        if gate:
            return gate
        from _lib.brand_validate import validate_brand_id
        try:
            brand_id = validate_brand_id(brand_id)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        body = request.get_json(silent=True) or {}
        media_id = body.get("media_id")
        if not isinstance(media_id, int) or media_id <= 0:
            return jsonify({"ok": False, "error": "media_id must be a positive integer"}), 400
        from _lib.publish_v1 import (
            get_publish_record,
            _record_path,
            ACTION_ATTACH_MEDIA,
            _append_history,
        )
        rec = get_publish_record(brand_id, publish_id)
        if not rec:
            return jsonify({"ok": False, "error": "publish record not found"}), 404
        rec["approved_featured_image_media_id"] = int(media_id)
        _append_history(rec, ACTION_ATTACH_MEDIA, actor="operator",
                        from_status=rec.get("status"), to_status=rec.get("status"),
                        result={"media_id": media_id})
        import time as _t
        rec["updated_at"] = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
        _record_path(rec["brand_id"], rec["publish_id"]).write_text(
            json.dumps(rec, indent=2, ensure_ascii=False)
        )
        return jsonify({"ok": True, "approved_featured_image_media_id": int(media_id), "publish_id": publish_id}), 200

    app.register_blueprint(bp)
    return bp
