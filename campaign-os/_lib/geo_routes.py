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


def _stage_sample_label(stage: str, n: int) -> str:
    """V1.1: Sample-size label that pairs with the stage so operators never
    see a meaningful-looking citation percentage when the sample is tiny."""
    if stage == "NO_DATA":
        return f"n={n} — NO DATA. Rate not reported."
    if stage == "BASELINE":
        return f"n={n} — BASELINE. First observation window. Rate is directional only."
    return f"n={n} — TRENDING. Rate is meaningful with this sample size."


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
        # V1.1 calibration (2026-10-01): canonical observation schema. The OS
        # can only ingest observations the operator pastes from a real LLM
        # answer. Each entry is tagged MANUAL_OBSERVATION by default. Future
        # automated capture would set source='AUTOMATED'.
        run_ts = _now_iso()
        entry = {
            "id": str(uuid.uuid4()),
            "operating_brand": brand,
            "canonical_query_id": body.get("canonical_query_id") or body.get("query_id") or None,
            "exact_prompt": body.get("exact_prompt") or body.get("prompt", ""),
            "model_provider": body.get("model_provider") or body.get("model", "unknown"),
            "model": body.get("model") or body.get("model_provider", "unknown"),
            "model_version": body.get("model_version") or None,
            "run_timestamp": body.get("run_timestamp") or run_ts,
            "added_at": run_ts,
            "answer_text": body.get("answer_text", ""),
            "brand_mentioned": bool(body.get("brand_mentioned") if body.get("brand_mentioned") is not None else body.get("mentions_brand", False)),
            "mentions_brand": bool(body.get("mentions_brand", False)),
            "cited": bool(body.get("cited", False)),
            "mentions_url": bool(body.get("mentions_url", False)),
            "cited_urls": body.get("cited_urls") or ([body["url_cited"]] if body.get("url_cited") else []),
            "url_cited": body.get("url_cited") or None,
            "competitor_mentions": body.get("competitor_mentions") or [],
            "source": "MANUAL_OBSERVATION",
            "actor": body.get("actor") or "heidi",
            "date": body.get("date") or datetime.date.today().isoformat(),
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

        # V1.1 calibration (2026-10-01): GEO score is split into two buckets.
        # OBSERVED AI PERFORMANCE is the primary score, computed from real
        # citation records. SITE READINESS is a supporting diagnostic from
        # the audit, NEVER blended into the GEO score.
        # Stage labels: NO_DATA (n<3), BASELINE (n=3-9), TRENDING (n>=10).

        def _stage(n: int) -> str:
            if n == 0:
                return "NO_DATA"
            if n < 3:
                return "NO_DATA"  # too small to call meaningful
            if n < 10:
                return "BASELINE"
            return "TRENDING"

        stage = _stage(total)

        # Citation rate (only meaningful when stage != NO_DATA).
        # V1.2.1 (2026-10-02): the canonical rule is "n < 3 → rates are null",
        # not "total == 0 → null". The previous branch (`if total == 0`)
        # computed non-null rates for n=1 and n=2, which contradicted the
        # NO_DATA stage. Operator directive: fix only this bug; do not
        # redesign the scorecard.
        if stage == "NO_DATA":
            citation_rate = None
            url_citation_rate = None
            competitor_share = None
            query_coverage = None
        else:
            cited = sum(1 for c in citations if c.get("mentions_brand") or c.get("brand_mentioned"))
            url_cited = sum(1 for c in citations if c.get("mentions_url") or c.get("cited"))
            citation_rate = round(cited / total * 100, 1)
            url_citation_rate = round(url_cited / total * 100, 1)
            # Competitor share: count citations where ANY competitor is mentioned
            competitor_mention_count = sum(
                1 for c in citations
                if isinstance(c.get("competitor_mentions"), list) and c["competitor_mentions"]
            )
            competitor_share = round(competitor_mention_count / total * 100, 1)
            # Query coverage: distinct canonical_query_ids that have observations
            query_ids = {c.get("canonical_query_id") for c in citations if c.get("canonical_query_id")}
            query_coverage = len(query_ids)

        # Weekly delta
        weekly_delta = None
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            recent = []
            older = []
            for c in citations:
                ts = c.get("added_at") or c.get("run_timestamp") or "1970"
                try:
                    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    continue
                if dt >= cutoff:
                    recent.append(c)
                else:
                    older.append(c)
            if recent and older and stage != "NO_DATA":
                recent_rate = sum(1 for c in recent if c.get("mentions_brand") or c.get("brand_mentioned")) / len(recent) * 100
                older_rate = sum(1 for c in older if c.get("mentions_brand") or c.get("brand_mentioned")) / len(older) * 100
                weekly_delta = round(recent_rate - older_rate, 1)
        except Exception:
            pass

        # Top models
        model_counts: Dict[str, int] = {}
        for c in citations:
            m = c.get("model") or c.get("model_provider") or "unknown"
            model_counts[m] = model_counts.get(m, 0) + 1
        top_models = sorted(model_counts.items(), key=lambda x: -x[1])[:5]

        # V1.1: Site readiness is fetched as a parallel diagnostic. It is
        # NOT part of the observed AI performance score.
        site_readiness = {"ok": False, "checks": [], "error": None}
        try:
            from _lib.geo_audit import run_geo_audit
            audit = run_geo_audit(brand, force_refresh=False)
            if audit.get("ok"):
                site_readiness = {
                    "ok": True,
                    "checks": [
                        {
                            "check": c.get("check"),
                            "signal_type": c.get("signal_type", "TECHNICAL_SEO"),
                            "status": c.get("status"),
                            "severity": c.get("severity"),
                            "excluded_from_score": c.get("excluded_from_score", False),
                        }
                        for c in audit.get("checks", [])
                    ],
                    "domain": audit.get("domain"),
                    "fetched_at": audit.get("fetched_at"),
                }
            else:
                site_readiness["error"] = audit.get("error")
        except Exception as e:
            site_readiness["error"] = str(e)

        return jsonify({
            "ok": True,
            "brand": brand,
            "stage": stage,
            "n": total,
            "sample_size_label": _stage_sample_label(stage, total),
            # OBSERVED AI PERFORMANCE — the primary GEO score
            "observed_ai_performance": {
                "citation_rate": citation_rate,  # % of pastes mentioning the brand
                "url_citation_rate": url_citation_rate,  # % of pastes citing the brand URL
                "query_coverage": query_coverage,  # distinct canonical queries with observations
                "competitor_share": competitor_share,  # % of answers mentioning a competitor
                "weekly_delta": weekly_delta,
                "top_models": [{"model": m, "count": n} for m, n in top_models],
                "recent": citations[-10:] if citations else [],
            },
            # SITE READINESS — supporting diagnostic, never blended into score
            "site_readiness": site_readiness,
            "disclaimer": (
                "Citation rate is only meaningful when n >= 3 observations. "
                "Below that the stage is NO_DATA and the rate is reported as null."
                if stage == "NO_DATA"
                else f"Sample size n={total} ({stage}). A single observation does "
                     "not represent general model behaviour."
            ),
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
            # V1.1 calibration (2026-10-01): default to MANUAL_APPROVAL_REQUIRED
            # so every code path is human-gated unless explicitly upgraded.
            # The audit_trail.approved_by stays null until an operator manually
            # confirms and the OS writes to WP.
            "status": "MANUAL_APPROVAL_REQUIRED",
            "check": check,
            "fix_id": fix_id,
            "brand": brand,
            "audit_trail": {
                "brand": brand,
                "check": check,
                "fix_id": fix_id,
                "ts": _now_iso(),
                "approved_by": None,
                "auto_written_to_wp": False,
            },
        }

        domain = _BRAND_DOMAINS.get(brand, "")

        if check == "missing_llms_txt":
            # Check if Yoast has an llms.txt endpoint first
            wp_resp = _wp_request(brand, "GET", "/llms")
            if wp_resp.get("ok"):
                result["status"] = "APPLIED"
                result["audit_trail"]["auto_written_to_wp"] = True
                result["details"] = wp_resp.get("data")
            else:
                content = _build_llms_txt_suggestion(brand)
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
                    result["audit_trail"]["auto_written_to_wp"] = True
                    result["details"]["note"] += " Yoast FAQ meta flag set on post. Operator still needs to add FAQ content via the editor."

        elif check == "missing_h1":
            result["details"] = {
                "note": "Yoast SEO manages H1 and meta descriptions in the WP editor. Programmatic write not available via REST in this module.",
                "fix": "Edit the page in WP, ensure the main heading is an <h1> tag, not bold text or <h2>. Save and update.",
                "brand": brand,
            }

        elif check == "missing_meta_description":
            result["details"] = {
                "note": "Add a meta description via the Yoast SEO snippet editor in the WP page/post editor.",
                "fix": "Open the page in WP → scroll to Yoast SEO panel → edit the snippet (meta description). Keep it 120–160 characters.",
                "brand": brand,
            }

        elif check == "missing_organization_schema":
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
            result["details"] = {
                "note": "Add Open Graph meta tags to the <head> of the page.",
                "fix": "In WP: use Yoast SEO → Social, or add to your theme's header.php",
                "og_tags": _build_og_suggestion(domain, brand),
            }

        elif check == "twitter_card":
            result["details"] = {
                "note": "Add Twitter Card meta tags to the <head> of the page.",
                "fix": "In WP: use Yoast SEO → Social → Twitter, or add to theme header.php",
                "twitter_tags": _build_twitter_suggestion(domain, brand),
            }

        elif check == "blog_post_schema":
            result["details"] = {
                "note": "Add Article/BlogPosting JSON-LD to recent blog posts. Most themes emit BlogPosting automatically; Yoast handles this when schema is enabled.",
                "instructions": "In WP → Settings → Reading → Theme, ensure 'Article' is set. Or install 'Schema & Structured Data for WP' plugin.",
            }

        elif check == "robots_review":
            # V1.1: robots.txt is held for human review — there is no clean
            # programmatic write path through WP REST. Return the current
            # and proposed states with per-line effect.
            from _lib.geo_audit import _build_robots_review
            review = _build_robots_review(brand)
            result["details"] = {
                "note": (
                    "robots.txt is a site-level file. There is no standard WP "
                    "REST endpoint to write it. The OS proposes a new robots.txt "
                    "with sitemap pointer + per-line effect; operator reviews "
                    "the diff and either pastes it into their hosting control "
                    "panel (Railway Nixpack static-files or cPanel File Manager) "
                    "or rejects the change. NEVER auto-write to live WP."
                ),
                "current": review.get("current_robots"),
                "proposed": review.get("fix_suggestion"),
                "classification": review.get("status"),
                "signal_type": "TECHNICAL_SEO",
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
