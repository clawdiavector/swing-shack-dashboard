"""
_lib/geo_routes.py — Flask Blueprint for GEO module.

Routes (session-auth only):
  GET    /api/geo/citations              ?brand=<id>     — list citation pastes
  POST   /api/geo/citations              body            — add a citation paste
  GET    /api/geo/scorecard              ?brand=<id>     — aggregated scorecard
  GET    /api/geo/watchlist             ?brand=<id>     — canonical query watchlist
  POST   /api/geo/watchlist             body            — add a watchlist query
  GET    /api/geo/audit                 ?brand=<id>     — GEO audit results
  POST   /api/geo/apply-fix             body            — apply a specific fix
  GET    /api/intel/geo-weekly-report   ?brand=<id>     — combined weekly report section
"""
from __future__ import annotations
import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")
BUNDLED_DATA_DIR = os.environ.get(
    "BUNDLED_DATA_DIR",
    str(Path(__file__).parent.parent / "data"),
)

VALID_BRANDS = ("swing-shack", "stick", "bag-drop")
_BRAND_DISPLAY = {
    "swing-shack": "Swing Shack",
    "stick": "Stick Golf",
    "bag-drop": "Bag Drop",
}

_BRAND_DOMAINS = {
    "swing-shack": "https://swingshack.co.za",
    "stick": "https://stickgolf.co.za",
    "bag-drop": "https://swingshack.co.za",
}

# Default watchlist queries (seeded if file is empty)
_DEFAULT_WATCHLIST = {
    "swing-shack": [
        "best indoor golf Johannesburg",
        "TrackMan fitting Johannesburg",
        "golf coaching JHB",
        "club fitting Johannesburg",
        "swing analysis Johannesburg",
    ],
    "stick": [
        "TrackMan fitting Paarl",
        "Cape Winelands golf",
        "golf coaching Paarl",
        "Vice Golf South Africa",
        "golf lessons for beginners South Africa",
    ],
    "bag-drop": [],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _data_path(filename: str) -> Path:
    p = Path(DATA_DIR) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _bundled_path(filename: str) -> Path:
    return Path(BUNDLED_DATA_DIR) / filename


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _auth_gate():
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
        if token:
            try:
                s.loads(token, max_age=60 * 60 * 24 * 30)
                return None
            except (BadSignature, SignatureExpired):
                pass
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer ") and len(auth.split(" ", 1)[1].strip()) > 0:
            return None
    except Exception:
        pass
    return jsonify({"ok": False, "error": "authentication required"}), 401


def _validate_brand(brand: str) -> str:
    if brand not in VALID_BRANDS:
        raise ValueError(f"brand must be one of: {', '.join(VALID_BRANDS)}")
    return brand


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


# ── Citations helpers ────────────────────────────────────────────────────────

def _citations_path(brand: str) -> Path:
    return _data_path(f"geo-citations-{brand}.json")


def _load_citations(brand: str) -> List[Dict]:
    path = _citations_path(brand)
    if path.exists():
        data = _load_json(path)
        if isinstance(data, list):
            return data
    return []


def _save_citation(brand: str, entry: Dict) -> None:
    path = _citations_path(brand)
    entries = _load_citations(brand)
    entries.append(entry)
    _save_json(path, entries)


def _delete_citation(brand: str, idx: int) -> bool:
    path = _citations_path(brand)
    entries = _load_citations(brand)
    if idx < 0 or idx >= len(entries):
        return False
    entries.pop(idx)
    _save_json(path, entries)
    return True


# ── Watchlist helpers ─────────────────────────────────────────────────────────

def _watchlist_path(brand: str) -> Path:
    return _data_path(f"geo-watchlist-{brand}.json")


def _load_watchlist(brand: str) -> List[Dict]:
    path = _watchlist_path(brand)
    data = _load_json(path)
    if isinstance(data, list):
        if len(data) == 0:
            # Seed with defaults
            _save_json(path, [{"query": q, "added_at": _now_iso()} for q in _DEFAULT_WATCHLIST.get(brand, [])])
            return [{"query": q, "added_at": _now_iso()} for q in _DEFAULT_WATCHLIST.get(brand, [])]
        return data
    # No file — seed defaults
    defaults = [{"query": q, "added_at": _now_iso()} for q in _DEFAULT_WATCHLIST.get(brand, [])]
    _save_json(path, defaults)
    return defaults


# ── Routes ────────────────────────────────────────────────────────────────────

def register_routes(app):
    bp = Blueprint("geo", __name__)

    # ── CITATIONS ──────────────────────────────────────────────────────────

    @bp.route("/api/geo/citations", methods=["GET"])
    def get_citations():
        auth = _auth_gate()
        if auth:
            return auth
        brand = request.args.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({
            "ok": True,
            "brand": brand,
            "citations": _load_citations(brand),
            "count": len(_load_citations(brand)),
        }), 200

    @bp.route("/api/geo/citations", methods=["POST"])
    def add_citation():
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        brand = body.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        entry = {
            "id": str(uuid.uuid4()),
            "brand": brand,
            "model": body.get("model", "unknown"),
            "prompt": body.get("prompt", ""),
            "answer_text": body.get("answer_text", ""),
            "mentions_brand": bool(body.get("mentions_brand", False)),
            "mentions_url": bool(body.get("mentions_url", False)),
            "url_cited": body.get("url_cited") or None,
            "date": body.get("date") or datetime.date.today().isoformat(),
            "added_at": _now_iso(),
        }
        _save_citation(brand, entry)
        return jsonify({"ok": True, "entry": entry}), 201

    @bp.route("/api/geo/citations/<int:idx>", methods=["DELETE"])
    def delete_citation(idx: int):
        auth = _auth_gate()
        if auth:
            return auth
        brand = request.args.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        ok = _delete_citation(brand, idx)
        if not ok:
            return jsonify({"ok": False, "error": f"citation index {idx} not found"}), 404
        return jsonify({"ok": True, "deleted": idx}), 200

    # ── SCORECARD ───────────────────────────────────────────────────────────

    @bp.route("/api/geo/scorecard", methods=["GET"])
    def get_scorecard():
        auth = _auth_gate()
        if auth:
            return auth
        brand = request.args.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        citations = _load_citations(brand)
        total = len(citations)

        # Citation rate
        if total == 0:
            citation_rate = None
            url_citation_rate = None
        else:
            cited = sum(1 for c in citations if c.get("mentions_brand"))
            url_cited = sum(1 for c in citations if c.get("mentions_url"))
            citation_rate = round(cited / total * 100, 1)
            url_citation_rate = round(url_cited / total * 100, 1)

        # Weekly delta
        weekly_delta = None
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            recent = [c for c in citations if datetime.datetime.fromisoformat(c.get("added_at", "1970").replace("Z", "+00:00")) >= cutoff]
            older = [c for c in citations if datetime.datetime.fromisoformat(c.get("added_at", "1970").replace("Z", "+00:00")) < cutoff]
            if recent and older:
                recent_rate = sum(1 for c in recent if c.get("mentions_brand")) / len(recent) * 100
                older_rate = sum(1 for c in older if c.get("mentions_brand")) / len(older) * 100
                weekly_delta = round(recent_rate - older_rate, 1)
        except Exception:
            pass

        # Top models
        model_counts: Dict[str, int] = {}
        for c in citations:
            m = c.get("model", "unknown")
            model_counts[m] = model_counts.get(m, 0) + 1
        top_models = sorted(model_counts.items(), key=lambda x: -x[1])[:5]

        return jsonify({
            "ok": True,
            "brand": brand,
            "total_queries": total,
            "citation_rate": citation_rate,
            "url_citation_rate": url_citation_rate,
            "weekly_delta": weekly_delta,
            "top_models": [{"model": m, "count": n} for m, n in top_models],
            "recent": citations[-10:] if citations else [],
            "generated_at": _now_iso(),
        }), 200

    # ── WATCHLIST ────────────────────────────────────────────────────────────

    @bp.route("/api/geo/watchlist", methods=["GET"])
    def get_watchlist():
        auth = _auth_gate()
        if auth:
            return auth
        brand = request.args.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({
            "ok": True,
            "brand": brand,
            "watchlist": _load_watchlist(brand),
            "count": len(_load_watchlist(brand)),
        }), 200

    @bp.route("/api/geo/watchlist", methods=["POST"])
    def add_watchlist():
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        brand = body.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        query = (body.get("query") or "").strip()
        if not query:
            return jsonify({"ok": False, "error": "query is required"}), 400
        region = body.get("region") or ""
        wl = _load_watchlist(brand)
        # Avoid duplicates
        existing = [w for w in wl if w.get("query", "").lower() == query.lower()]
        if existing:
            return jsonify({"ok": True, "entry": existing[0], "note": "already exists"}), 200
        entry = {"query": query, "region": region, "added_at": _now_iso()}
        wl.append(entry)
        _save_json(_watchlist_path(brand), wl)
        return jsonify({"ok": True, "entry": entry}), 201

    @bp.route("/api/geo/watchlist", methods=["DELETE"])
    def delete_watchlist():
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        brand = body.get("brand", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        query = (body.get("query") or "").strip()
        wl = _load_watchlist(brand)
        before = len(wl)
        wl = [w for w in wl if w.get("query", "").lower() != query.lower()]
        if len(wl) == before:
            return jsonify({"ok": False, "error": "query not found in watchlist"}), 404
        _save_json(_watchlist_path(brand), wl)
        return jsonify({"ok": True, "removed": query}), 200

    # ── AUDIT ────────────────────────────────────────────────────────────────

    @bp.route("/api/geo/audit", methods=["GET"])
    def get_audit():
        auth = _auth_gate()
        if auth:
            return auth
        brand = request.args.get("brand", "")
        force = request.args.get("force_refresh", "").lower() in ("1", "true", "yes")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        try:
            from _lib.geo_audit import run_geo_audit
            result = run_geo_audit(brand, force_refresh=force)
            return jsonify(result), 200 if result.get("ok") else 500
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── APPLY FIX ────────────────────────────────────────────────────────────

    @bp.route("/api/geo/apply-fix", methods=["POST"])
    def apply_fix():
        auth = _auth_gate()
        if auth:
            return auth
        body = request.get_json(silent=True) or {}
        brand = body.get("brand", "")
        check = body.get("check", "")
        fix_id = body.get("fix_id", "")
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        if not check:
            return jsonify({"ok": False, "error": "check is required"}), 400

        from _lib.geo_audit import (
            _build_llms_txt_suggestion,
            _build_faqpage_suggestion,
            _build_org_schema_suggestion,
            _build_blog_schema_suggestion,
            _build_og_suggestion,
            _build_twitter_suggestion,
            _wp_request,
        )

        result: Dict[str, Any] = {
            "status": "MANUAL_APPROACH_REQUIRED",
            "check": check,
            "fix_id": fix_id,
            "brand": brand,
            "audit_trail": {
                "brand": brand,
                "check": check,
                "fix_id": fix_id,
                "ts": _now_iso(),
            },
        }

        domain = _BRAND_DOMAINS.get(brand, "")

        if check == "missing_llms_txt":
            # Check if Yoast has an llms.txt endpoint first
            wp_resp = _wp_request(brand, "GET", "/llms")
            if wp_resp.get("ok"):
                result["status"] = "APPLIED"
                result["details"] = wp_resp.get("data")
            else:
                content = _build_llms_txt_suggestion(brand)
                result["status"] = "MANUAL_APPROACH_REQUIRED"
                result["details"] = {
                    "note": "WP REST has no standard llms.txt endpoint. Paste the content below into a file named llms.txt at the domain root via your hosting provider (Railway Nixpack or cPanel File Manager).",
                    "content": content,
                    "paste_instruction": (
                        f"1. Save the content below as a file named 'llms.txt'\n"
                        f"2. Upload it to the web root of {domain}\n"
                        f"3. Verify it loads at {domain}/llms.txt\n"
                        f"4. Yoast SEO Premium v28+ will auto-reference it."
                    ),
                }

        elif check == "missing_faqpage_schema":
            # Return the JSON-LD block for operator to paste into a blog post
            faq_json = _build_faqpage_suggestion(brand)
            result["status"] = "MANUAL_APPROACH_REQUIRED"
            result["details"] = {
                "note": "Add FAQPage JSON-LD to a WP blog post. Use a Custom HTML block or a Yoast FAQ block.",
                "jsonld": faq_json,
                "instructions": (
                    "1. Create or edit a blog post in WP\n"
                    "2. Add a 'Custom HTML' block\n"
                    "3. Paste the JSON-LD below inside <script type='application/ld+json'>...</script>\n"
                    "4. Or use Yoast SEO → FAQ block in the Gutenberg editor\n"
                    "5. Publish or update the post"
                ),
            }
            # Try to auto-patch via WP REST if a post ID is provided
            post_id = body.get("post_id")
            if post_id:
                # Try patching with Yoast meta
                patch_resp = _wp_request(
                    brand, "POST",
                    f"/posts/{post_id}",
                    {
                        "meta": {
                            "_yoast_wpseo_faq": "true",
                        }
                    }
                )
                if patch_resp.get("ok"):
                    result["auto_patch"] = patch_resp.get("data")
                    result["status"] = "PARTIAL_APPLIED"
                    result["details"]["note"] += " Yoast FAQ meta flag set on post. Operator still needs to add FAQ content via the editor."

        elif check == "missing_h1":
            result["status"] = "MANUAL_APPROACH_REQUIRED"
            result["details"] = {
                "note": "Yoast SEO manages H1 and meta descriptions in the WP editor. Programmatic write not available via REST in this module.",
                "fix": "Edit the page in WP, ensure the main heading is an <h1> tag, not bold text or <h2>. Save and update.",
                "brand": brand,
            }

        elif check == "missing_meta_description":
            result["status"] = "MANUAL_APPROACH_REQUIRED"
            result["details"] = {
                "note": "Add a meta description via the Yoast SEO snippet editor in the WP page/post editor.",
                "fix": "Open the page in WP → scroll to Yoast SEO panel → edit the snippet (meta description). Keep it 120–160 characters.",
                "brand": brand,
            }

        elif check == "missing_organization_schema":
            result["status"] = "MANUAL_APPROACH_REQUIRED"
            result["details"] = {
                "note": "Organization schema is theme-controlled. Add via a child theme or a Schema plugin.",
                "jsonld": _build_org_schema_suggestion(brand),
                "instructions": (
                    "Option A (Schema plugin): Install 'Schema & Structured Data for WP' or 'WP SEO Structured Data Schema'\n"
                    f"Option B (child theme): Add the JSON-LD below to your theme's functions.php or a custom plugin\n"
                    "Option C (Yoast Premium): Use Yoast → Schema → Organization"
                ),
            }

        elif check == "missing_faq":
            result["details"] = {
                "note": "Add an FAQ section to this page. Use the Yoast FAQ block or Custom HTML.",
                "jsonld": _build_faqpage_suggestion(brand),
                "instructions": "In WP editor: add a Yoast FAQ block, or add a Custom HTML block with the JSON-LD above.",
            }

        elif check == "og_tags":
            result["status"] = "MANUAL_APPROACH_REQUIRED"
            result["details"] = {
                "note": "Add Open Graph meta tags to the <head> of the page.",
                "fix": "In WP: use Yoast SEO → Social, or add to your theme's header.php",
                "og_tags": _build_og_suggestion(domain, brand),
            }

        elif check == "twitter_card":
            result["status"] = "MANUAL_APPROACH_REQUIRED"
            result["details"] = {
                "note": "Add Twitter Card meta tags to the <head> of the page.",
                "fix": "In WP: use Yoast SEO → Social → Twitter, or add to theme header.php",
                "twitter_tags": _build_twitter_suggestion(domain, brand),
            }

        else:
            result["status"] = "UNHANDLED_CHECK"
            result["details"] = {"note": f"check '{check}' is not yet handled in apply-fix. Manual review required."}

        return jsonify(result), 200

    # ── GEO WEEKLY REPORT ───────────────────────────────────────────────────

    @bp.route("/api/intel/geo-weekly-report", methods=["GET"])
    def geo_weekly_report():
        auth = _auth_gate()
        if auth:
            return auth
        brand = request.args.get("brand", "")
        as_of = request.args.get("as_of", datetime.date.today().isoformat())
        try:
            brand = _validate_brand(brand)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        try:
            from _lib.geo_audit import run_geo_audit
        except ImportError:
            return jsonify({"ok": False, "error": "geo_audit module not available"}), 503

        audit = run_geo_audit(brand)
        citations = _load_citations(brand)
        watchlist = _load_watchlist(brand)

        # Scorecard
        total = len(citations)
        cited = sum(1 for c in citations if c.get("mentions_brand"))
        url_cited = sum(1 for c in citations if c.get("mentions_url"))
        citation_rate = round(cited / total * 100, 1) if total > 0 else 0.0
        url_rate = round(url_cited / total * 100, 1) if total > 0 else 0.0

        # Top blockers from audit
        blockers = [
            {"check": c["check"], "status": c["status"], "severity": c["severity"], "message": c["message"]}
            for c in audit.get("checks", [])
            if c.get("status") != "OK" and c.get("severity") in ("high", "medium")
        ]

        # Last 5 citations
        recent_5 = citations[-5:] if citations else []

        return jsonify({
            "ok": True,
            "brand": brand,
            "as_of": as_of,
            "section": "GEO & AI Citation Health",
            "scorecard": {
                "total_queries": total,
                "citation_rate": citation_rate,
                "url_citation_rate": url_rate,
                "watchlist_count": len(watchlist),
                "cited": cited,
                "url_cited": url_cited,
            },
            "audit_blockers": blockers,
            "watchlist": watchlist,
            "recent_citations": [
                {
                    "model": c.get("model"),
                    "mentions_brand": c.get("mentions_brand"),
                    "mentions_url": c.get("mentions_url"),
                    "date": c.get("date"),
                }
                for c in recent_5
            ],
            "generated_at": _now_iso(),
        }), 200

    # Register with the Flask app
    app.register_blueprint(bp)
