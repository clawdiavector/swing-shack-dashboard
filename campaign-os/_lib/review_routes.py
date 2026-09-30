"""
review_routes.py — Flask routes for the Campaign OS Human Review Layer V1.

This module is imported by campaign-os/app.py near the existing
create/v1 routes. It wires the review module (_lib/review.py) to the
HTTP layer and provides:

HTML:
  GET /review/v1/<brand_id>                                   (queue page)
  GET /review/v1/<brand_id>/<brief_id>                        (article review page)

API:
  GET  /api/review/v1/queue/<brand_id>                         (queue JSON)
  GET  /api/review/v1/<brand_id>/<brief_id>                    (item detail JSON)
  POST /api/review/v1/<brand_id>/<brief_id>/open               (create-or-load)
  POST /api/review/v1/<brand_id>/<brief_id>/sections/<id>/approve
  POST /api/review/v1/<brand_id>/<brief_id>/sections/<id>/edit
  POST /api/review/v1/<brand_id>/<brief_id>/sections/<id>/reject
  POST /api/review/v1/<brand_id>/<brief_id>/sections/<id>/request-rewrite
  POST /api/review/v1/<brand_id>/<brief_id>/sections/<id>/apply-rewrite
  POST /api/review/v1/<brand_id>/<brief_id>/comments
  POST /api/review/v1/<brand_id>/<brief_id>/comments/<id>/resolve
  GET  /api/review/v1/<brand_id>/<brief_id>/history
  GET  /api/review/v1/<brand_id>/<brief_id>/article            (current article body)
  GET  /api/review/v1/<brand_id>/<brief_id>/blockers           (approval blockers)
  POST /api/review/v1/<brand_id>/<brief_id>/approve
  POST /api/review/v1/<brand_id>/<brief_id>/reject

Identity:
  The reviewer_id is taken from the authenticated session (operator
  identity) — never invented. If session auth isn't available, the
  identity falls back to a stable "session-<id>" derived from the
  request (no fake names).

This module does NOT add publishing routes, WordPress routes, or any
auto-approve logic. Approval requires an explicit human action.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from flask import Blueprint, jsonify, request, render_template_string
except ImportError:  # the route module is import-checked by app.py at boot
    Blueprint = None  # type: ignore
    jsonify = None  # type: ignore
    request = None  # type: ignore
    render_template_string = None  # type: ignore

from . import review as _review


# ---------------------------------------------------------------------------
# Reviewer identity helper
# ---------------------------------------------------------------------------

def _resolve_reviewer_id(req) -> str:
    """Get the authenticated reviewer identity.

    Order of precedence:
    1. Session cookie (the existing Campaign OS /login session)
    2. Bearer token (the existing COS_JOB_TOKEN or human-token)
    3. Stable session fingerprint (no fake names — never 'Admin' / 'AI Reviewer')
    """
    try:
        # Session-based auth (the standard Campaign OS path)
        if req and hasattr(req, "session"):
            sess = req.session
            # The Campaign OS login flow sets session['authenticated'] = True
            # and session.get('username') / session.get('user_id') when available.
            if sess.get("authenticated"):
                return (
                    sess.get("user_id")
                    or sess.get("username")
                    or sess.get("reviewer_id")
                    or f"session-{sess.sid if hasattr(sess, 'sid') else 'auth'}"
                )
        # Bearer token (job / programmatic)
        if req and hasattr(req, "headers"):
            auth = req.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                tok = auth.split(" ", 1)[1].strip()
                if tok and len(tok) < 64:
                    return f"bearer-{tok[:12]}"
        # Stable request fingerprint — no names
        if req and hasattr(req, "remote_addr"):
            return f"session-{req.remote_addr}"
    except Exception:
        pass
    return "anonymous"


# ---------------------------------------------------------------------------
# Blueprint registration helper (called from app.py)
# ---------------------------------------------------------------------------

def register_routes(app):
    """Register the review Blueprint against the existing Flask app."""
    if Blueprint is None:
        return  # flask not installed — nothing to do

    bp = Blueprint("review_v1", __name__)

    # ---- HTML pages ----------------------------------------------------

    @bp.route("/review/v1/<brand_id>", methods=["GET"])
    def review_queue_html(brand_id):
        return _render_queue_page(brand_id)

    @bp.route("/review/v1/<brand_id>/<brief_id>", methods=["GET"])
    def review_item_html(brand_id, brief_id):
        return _render_item_page(brand_id, brief_id)

    # ---- API: queue ----------------------------------------------------

    @bp.route("/api/review/v1/queue/<brand_id>", methods=["GET"])
    def review_queue_api(brand_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        if brand_id not in ("stick", "swing-shack", "bag-drop"):
            return jsonify({"ok": False, "error": "invalid brand"}), 400
        return jsonify({"ok": True, "queue": _review.get_review_queue(brand_id)}), 200

    # ---- API: item -----------------------------------------------------

    @bp.route("/api/review/v1/<brand_id>/<brief_id>", methods=["GET"])
    def review_item_api(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        return jsonify(_review.get_review_detail(brand_id, f"r_{brief_id}")), 200

    # ---- API: open -----------------------------------------------------

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/open", methods=["POST"])
    def review_open_api(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        actor = _resolve_reviewer_id(request)
        r = _review.create_or_get_review(brand_id, brief_id, actor)
        if not r.get("ok"):
            return jsonify(r), 404
        return jsonify(r), 200

    # ---- API: section actions -----------------------------------------

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/sections/<section_id>/approve",
              methods=["POST"])
    def review_section_approve(brand_id, brief_id, section_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        actor = _resolve_reviewer_id(request)
        r = _review.approve_section(brand_id, f"r_{brief_id}", section_id, actor)
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/sections/<section_id>/edit",
              methods=["POST"])
    def review_section_edit(brand_id, brief_id, section_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        new_body = body.get("body")
        reason = body.get("reason")
        if not isinstance(new_body, str):
            return jsonify({"ok": False, "error": "body (string) required"}), 400
        actor = _resolve_reviewer_id(request)
        r = _review.edit_section(
            brand_id, f"r_{brief_id}", section_id, new_body, actor, reason
        )
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/sections/<section_id>/reject",
              methods=["POST"])
    def review_section_reject(brand_id, brief_id, section_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        reason = body.get("reason")
        if not reason:
            return jsonify({"ok": False, "error": "reason required"}), 400
        actor = _resolve_reviewer_id(request)
        r = _review.reject_section(
            brand_id, f"r_{brief_id}", section_id, actor, reason
        )
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/sections/<section_id>/restore",
              methods=["POST"])
    def review_section_restore(brand_id, brief_id, section_id):
        """Reverse a previous REJECT_SECTION so the section is reviewable
        again. Completion of Review V1, not a new V2. Idempotent on
        non-rejected sections. Does NOT auto-approve; does NOT delete
        comments/history; does NOT touch the Writer artifact."""
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        actor = _resolve_reviewer_id(request)
        r = _review.restore_section(
            brand_id, f"r_{brief_id}", section_id, actor,
            reason=body.get("reason"),
        )
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/sections/<section_id>/request-rewrite",
              methods=["POST"])
    def review_section_request_rewrite(brand_id, brief_id, section_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        instruction = body.get("instruction")
        if not instruction:
            return jsonify({"ok": False, "error": "instruction required"}), 400
        actor = _resolve_reviewer_id(request)
        r = _review.request_rewrite(
            brand_id, f"r_{brief_id}", section_id, actor, instruction
        )
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/sections/<section_id>/apply-rewrite",
              methods=["POST"])
    def review_section_apply_rewrite(brand_id, brief_id, section_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        new_body = body.get("body")
        if not isinstance(new_body, str):
            return jsonify({"ok": False, "error": "body (string) required"}), 400
        actor = _resolve_reviewer_id(request)
        r = _review.apply_rewritten_section(
            brand_id, f"r_{brief_id}", section_id, new_body, actor
        )
        return jsonify(r), 200 if r.get("ok") else 400

    # ---- API: comments -------------------------------------------------

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/comments", methods=["POST"])
    def review_add_comment(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        text = body.get("body")
        if not text:
            return jsonify({"ok": False, "error": "body required"}), 400
        actor = _resolve_reviewer_id(request)
        r = _review.add_comment(
            brand_id, f"r_{brief_id}",
            body=text,
            actor=actor,
            blocking=bool(body.get("blocking", False)),
            section_id=body.get("section_id"),
            claim_id=body.get("claim_id"),
        )
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/comments/<comment_id>/resolve",
              methods=["POST"])
    def review_resolve_comment(brand_id, brief_id, comment_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        actor = _resolve_reviewer_id(request)
        r = _review.resolve_comment(brand_id, f"r_{brief_id}", comment_id, actor)
        return jsonify(r), 200 if r.get("ok") else 400

    # ---- API: history, article, blockers ------------------------------

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/history", methods=["GET"])
    def review_history(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        return jsonify({
            "ok": True,
            "history": _review.get_revision_history(brand_id, f"r_{brief_id}"),
        }), 200

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/article", methods=["GET"])
    def review_article(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        record = _review.get_review_item(brand_id, f"r_{brief_id}")
        if record is None:
            return jsonify({"ok": False, "error": "review not found"}), 404
        return jsonify({"ok": True, **_review.assemble_human_facing_article(record)}), 200

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/blockers", methods=["GET"])
    def review_blockers(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        record = _review.get_review_item(brand_id, f"r_{brief_id}")
        if record is None:
            return jsonify({"ok": False, "error": "review not found"}), 404
        from .review import _compute_approval_blockers
        blockers = _compute_approval_blockers(record)
        return jsonify({"ok": True, "blockers": blockers}), 200

    # ---- API: approve / reject ----------------------------------------

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/approve", methods=["POST"])
    def review_approve(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        actor = _resolve_reviewer_id(request)
        r = _review.approve_for_publishing(brand_id, f"r_{brief_id}", actor)
        return jsonify(r), 200 if r.get("ok") else 400

    @bp.route("/api/review/v1/<brand_id>/<brief_id>/reject", methods=["POST"])
    def review_reject(brand_id, brief_id):
        if not _is_authed(request):
            return jsonify({"ok": False, "error": "auth required"}), 401
        body = request.get_json(silent=True) or {}
        reason = body.get("reason")
        explanation = body.get("explanation")
        if not reason:
            return jsonify({"ok": False, "error": "reason required"}), 400
        actor = _resolve_reviewer_id(request)
        r = _review.reject_draft(
            brand_id, f"r_{brief_id}", actor, reason, explanation
        )
        return jsonify(r), 200 if r.get("ok") else 400

    app.register_blueprint(bp)


# ---------------------------------------------------------------------------
# Auth helper — uses the same pattern as the existing create/v1 routes.
# ---------------------------------------------------------------------------

def _is_authed(req) -> bool:
    """Mirror Campaign OS's existing _is_authed() — checks the signed
    cos_session cookie via the app's serializer. Falls back to bearer
    token for programmatic access."""
    try:
        from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
        import os
        secret = (
            os.environ.get("CAMPAIGN_OS_SECRET")
            or os.environ.get("SESSION_SECRET")
            or os.environ.get("CAMPAIGN_OS_PASSWORD")
            or "dev-secret"
        )
        s = URLSafeTimedSerializer(secret)
        # The Campaign OS app uses cookie name "cos_session" (see SESSION_COOKIE
        # in app.py); Flask's default SESSION_COOKIE_NAME is "session" but the
        # /login flow explicitly sets cos_session, so we hardcode.
        token = req.cookies.get("cos_session")
        if token:
            try:
                s.loads(token, max_age=60 * 60 * 24 * 30)
                return True
            except (BadSignature, SignatureExpired):
                return False
        # Bearer token (programmatic / job)
        auth = req.headers.get("Authorization", "")
        if auth.lower().startswith("bearer ") and len(auth.split(" ", 1)[1].strip()) > 0:
            return True
    except Exception:
        pass
    return False




def _render_queue_page(brand_id: str):
    return render_template_string(QUEUE_HTML, brand_id=brand_id)


def _render_item_page(brand_id: str, brief_id: str):
    return render_template_string(
        ITEM_HTML,
        brand_id=brand_id,
        brief_id=brief_id,
        title=brief_id,
        status="DRAFT_FOR_REVIEW",
    )
