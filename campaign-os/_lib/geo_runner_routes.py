"""
_lib/geo_runner_routes.py — Flask Blueprint exposing GEO V1.2 runner routes.

Adds 5 read/write endpoints on top of the frozen V1.1 GEO module. None of
these endpoints modify the V1.1 scorecard logic; they only persist new
observations with source=AUTOMATED_OBSERVATION and surface_type=API_MODEL,
which the scorecard V1.1 already ingests.

Routes:
  POST /api/geo/runner/run-one             body: brand, query, model, grounding
  POST /api/geo/runner/run-watchlist       body: brand, model, grounding
  POST /api/geo/runner/run-all             body: model, grounding
  GET  /api/geo/runner/observations        ?brand=&provider=&model=&grounding=&source=&date_from=&date_to=
  POST /api/geo/runner/cost-estimate       body: queries_per_week, web_grounded_calls, ungrounded_calls

All endpoints session-auth via the same gate geo_routes uses.
Schedule is NOT created here. heidi.txt [1555477377310523394] section 9: hold
the schedule until cost + output quality are reviewed by the operator.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from _lib.geo_runner import (
    citation_metrics,
    filter_observations,
    run_brand_watchlist,
    run_one_query,
    cost_estimate,
    _data_dir,
    _load_citations,
)


# ── Auth gate (mirror GEO_routes._auth_gate) ──────────────────────────────────


def _auth_gate():
    import os
    try:
        from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
        secret = (
            os.environ.get("CAMPAIGN_OS_SECRET")
            or os.environ.get("SESSION_SECRET")
            or os.environ.get("CAMPAIGN_OS_PASSWORD")
            or "dev-secret"
        )
        s = URLSafeTimedSerializer(secret)
        token = request.cookies.get("cos_session")
        if not token:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        try:
            s.loads(token, max_age=60 * 60 * 24 * 14)
            return None
        except (BadSignature, SignatureExpired):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
    except Exception:
        return jsonify({"ok": False, "error": "auth unavailable"}), 503


VALID_BRANDS = {"swing-shack", "stick", "bag-drop"}


def _validate_brand(brand: str) -> str:
    if brand not in VALID_BRANDS:
        raise ValueError(f"brand must be one of: {', '.join(sorted(VALID_BRANDS))}")
    return brand


# ── Routes ─────────────────────────────────────────────────────────────────


def register_routes(app):
    bp = Blueprint("geo_runner", __name__)

    # ── POST /api/geo/runner/run-one ─────────────────────────────────────

    @bp.route("/api/geo/runner/run-one", methods=["POST"])
    def runner_run_one():
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        try:
            brand = _validate_brand(body.get("brand", ""))
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        query = (body.get("query") or "").strip()
        if not query:
            return jsonify({"ok": False, "error": "query is required"}), 400
        model = body.get("model", "gpt-4o-mini")
        grounding = body.get("grounding", "WEB_GROUNDED")
        try:
            result = run_one_query(
                brand=brand,
                query=query,
                model=model,
                grounding=grounding,
                country=body.get("country", "South Africa"),
                locale=body.get("locale", "en-ZA"),
                query_id=body.get("query_id"),
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"runner failed: {e}"}), 500
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    # ── POST /api/geo/runner/run-watchlist ───────────────────────────────

    @bp.route("/api/geo/runner/run-watchlist", methods=["POST"])
    def runner_run_watchlist():
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        try:
            brand = _validate_brand(body.get("brand", ""))
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        try:
            result = run_brand_watchlist(
                brand=brand,
                model=body.get("model", "gpt-4o-mini"),
                grounding=body.get("grounding", "WEB_GROUNDED"),
                country=body.get("country", "South Africa"),
                locale=body.get("locale", "en-ZA"),
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"runner failed: {e}"}), 500
        return jsonify(result), 200

    # ── POST /api/geo/runner/run-all ─────────────────────────────────────

    @bp.route("/api/geo/runner/run-all", methods=["POST"])
    def runner_run_all():
        """Run every enabled watchlist across every brand. Disabled
        brands are skipped silently."""
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        model = body.get("model", "gpt-4o-mini")
        grounding = body.get("grounding", "WEB_GROUNDED")
        brands = body.get("brands") or sorted(VALID_BRANDS)
        per_brand = []
        total_created = 0
        total_failed = 0
        for b in brands:
            try:
                _validate_brand(b)
            except ValueError:
                continue
            r = run_brand_watchlist(
                brand=b,
                model=model,
                grounding=grounding,
            )
            per_brand.append(
                {
                    "brand": b,
                    "observations_created": r.get("observations_created", 0),
                    "observations_failed": r.get("observations_failed", 0),
                    "watchlist_count": r.get("watchlist_count", 0),
                }
            )
            total_created += r.get("observations_created", 0)
            total_failed += r.get("observations_failed", 0)
        return jsonify(
            {
                "ok": True,
                "model": model,
                "grounding": grounding,
                "observations_created": total_created,
                "observations_failed": total_failed,
                "per_brand": per_brand,
            }
        ), 200

    # ── GET /api/geo/runner/observations ──────────────────────────────────

    @bp.route("/api/geo/runner/observations", methods=["GET"])
    def runner_observations():
        """Read observations from the canonical geo-citations-<brand>.json
        with filter axes (provider, model, grounding_type, source, date
        range). Returns the filtered list AND metrics computed from the
        filtered list only — so consumer-UI rows never mix invisibly with
        API rows."""
        auth = _auth_gate()
        if auth:
            return auth
        brand_arg = request.args.get("brand", "")
        try:
            brand = _validate_brand(brand_arg)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        source = request.args.get("source") or None
        grounding = request.args.get("grounding_type") or request.args.get("grounding") or None
        provider = request.args.get("provider") or None
        model = request.args.get("model") or None
        date_from = request.args.get("date_from") or None
        date_to = request.args.get("date_to") or None

        all_obs = _load_citations(brand)
        filtered = filter_observations(
            all_obs,
            source=source,
            grounding_type=grounding,
            provider=provider,
            model=model,
            date_from=date_from,
            date_to=date_to,
        )
        metrics = citation_metrics(filtered)

        return jsonify(
            {
                "ok": True,
                "brand": brand,
                "filters_applied": {
                    "source": source,
                    "grounding_type": grounding,
                    "provider": provider,
                    "model": model,
                    "date_from": date_from,
                    "date_to": date_to,
                },
                "metrics": metrics,
                "observations": filtered,
                "total_in_brand": len(all_obs),
                "filtered_count": len(filtered),
            }
        ), 200

    # ── POST /api/geo/runner/cost-estimate ────────────────────────────────

    @bp.route("/api/geo/runner/cost-estimate", methods=["POST"])
    def runner_cost_estimate():
        """Forecast USD cost for a proposed schedule. Schedule is NOT created."""
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        try:
            qpw = int(body.get("queries_per_week", 0))
            wg = int(body.get("web_grounded_calls", 0))
            ung = int(body.get("ungrounded_calls", 0))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "queries_per_week, web_grounded_calls, ungrounded_calls must be ints"}), 400
        if qpw < 0 or wg < 0 or ung < 0:
            return jsonify({"ok": False, "error": "counts cannot be negative"}), 400
        if wg + ung != qpw:
            return jsonify(
                {
                    "ok": False,
                    "error": f"web_grounded_calls ({wg}) + ungrounded_calls ({ung}) must equal queries_per_week ({qpw})",
                }
            ), 400
        est = cost_estimate(
            queries_per_week=qpw,
            web_grounded_calls=wg,
            ungrounded_calls=ung,
        )
        est["schedule_enabled"] = False  # explicit gate per spec
        return jsonify({"ok": True, "estimate": est}), 200

    app.register_blueprint(bp)