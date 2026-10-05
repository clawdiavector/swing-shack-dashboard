"""ClubLab read-only stats pull — layer-2 job (GET-only + auth login)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..errors import describe_exception
from ..layer1._io import atomic_write, data_dir, utc_now_iso

SNAPSHOT_NAME = "clublab-snapshot.json"
META_NAME = "clublab-snapshot.meta.json"
SCHEMA = "campaign-os/clublab-snapshot/v1"

DEFAULT_ORIGIN = "https://clublab.app"
CREDENTIALS_FILE = Path(
    "/home/kyle/finder-workspace/repos/work/ClubLab/.cursor/skills/clublab-agent/config/credentials-external.env"
)

DENY_KEYS = frozenset(
    {
        "firstname",
        "lastname",
        "fullname",
        "email",
        "phone",
        "clientdisplayname",
        "reviewtext",
        "reviewbody",
        "comments",
        "photo",
        "imageurl",
    }
)

CRM_DASHBOARD_DROP = frozenset({"topAtRisk", "top_at_risk", "topatrisk"})

REQUIRED_GET_PATHS = (
    "/api/v1/facilities",
    "/api/v1/crm/dashboard/summary",
    "/api/v1/crm/reports/summary",
    "/api/v1/crm/segments",
    "/api/v1/orderme/orders/summary",
    "/api/v1/fitme/summary",
    "/api/v1/fitme/equipment/top",
    "/api/v1/costme/catalogue",
    "/api/v1/Reports/session-summary",
    "/api/v1/Reports/tag-frequency",
)

OPTIONAL_GET_PATHS = ("/api/v1/fitme/timeline",)

_http_client_factory: Callable[[], Any] | None = None


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", key).lower()


def _sanitize_value(value: Any, stripped: list[str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _norm_key(k) in DENY_KEYS:
                stripped.append(k)
                continue
            out[k] = _sanitize_value(v, stripped)
        return out
    if isinstance(value, list):
        return [_sanitize_value(item, stripped) for item in value]
    return value


def sanitize_tree(value: Any) -> tuple[Any, list[str]]:
    stripped: list[str] = []
    cleaned = _sanitize_value(value, stripped)
    return cleaned, stripped


def _drop_keys(obj: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    drop_norm = {_norm_key(k) for k in keys}
    return {k: v for k, v in obj.items() if _norm_key(k) not in drop_norm}


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def load_clublab_env() -> None:
    """Populate CLUBLAB_* from process env or credentials file (never log values)."""
    if (os.environ.get("CLUBLAB_TOKEN") or "").strip():
        return
    if (os.environ.get("CLUBLAB_EMAIL") or "").strip() and (os.environ.get("CLUBLAB_PASSWORD") or "").strip():
        return
    parsed = _parse_env_file(CREDENTIALS_FILE)
    for key in ("CLUBLAB_EMAIL", "CLUBLAB_PASSWORD", "CLUBLAB_TOKEN", "CLUBLAB_ORIGIN"):
        if not os.environ.get(key) and parsed.get(key):
            os.environ[key] = parsed[key]


@dataclass
class HttpResponse:
    status: int
    body: Any
    url: str


class ClublabHttpClient:
    def __init__(self, origin: str, token: str, timeout: float = 60.0) -> None:
        self.origin = origin.rstrip("/")
        self.token = token
        self.timeout = timeout

    def get(self, path: str, *, facility_id: str | None = None) -> HttpResponse:
        query = f"?{urlencode({'facilityId': facility_id})}" if facility_id else ""
        url = f"{self.origin}{path}{query}"
        req = Request(url, method="GET", headers={"Authorization": f"Bearer {self.token}"})
        return self._request(req, url)

    def post_json(self, path: str, body: dict[str, Any]) -> HttpResponse:
        url = f"{self.origin}{path}"
        data = json.dumps(body).encode("utf-8")
        req = Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
        )
        return self._request(req, url)

    def _request(self, req: Request, url: str) -> HttpResponse:
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = getattr(resp, "status", 200) or 200
        except HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read().decode("utf-8")
            except Exception:  # noqa: BLE001
                raw = ""
            raise ClublabPullError(status, url, raw) from exc
        except URLError as exc:
            raise ClublabPullError(0, url, describe_exception(exc)) from exc
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return HttpResponse(status=status, body=parsed, url=url)


class ClublabPullError(Exception):
    def __init__(self, status: int, url: str, detail: str = "") -> None:
        self.status = status
        self.url = url
        self.detail = detail
        super().__init__(f"HTTP {status} {url}")


def login_token(origin: str) -> str:
    token = (os.environ.get("CLUBLAB_TOKEN") or "").strip()
    if token:
        return token
    email = (os.environ.get("CLUBLAB_EMAIL") or "").strip()
    password = (os.environ.get("CLUBLAB_PASSWORD") or "").strip()
    if not email or not password:
        raise ClublabPullError(401, f"{origin}/api/v1/auth/login", "missing CLUBLAB_EMAIL or CLUBLAB_PASSWORD")
    client = ClublabHttpClient(origin, token="")
    req = Request(
        f"{origin}/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            status = getattr(resp, "status", 200) or 200
    except HTTPError as exc:
        raise ClublabPullError(exc.code, f"{origin}/api/v1/auth/login", "") from exc
    doc = json.loads(raw) if raw else {}
    if not isinstance(doc, dict):
        raise ClublabPullError(status, f"{origin}/api/v1/auth/login", "invalid login response")
    data = doc.get("data")
    tok = None
    if isinstance(data, dict):
        tok = data.get("accessToken") or data.get("token") or data.get("access_token")
    if not tok:
        tok = doc.get("token") or doc.get("accessToken") or doc.get("access_token")
    if not tok:
        raise ClublabPullError(status, f"{origin}/api/v1/auth/login", "no token in response")
    return str(tok)


def _build_client() -> ClublabHttpClient:
    if _http_client_factory is not None:
        return _http_client_factory()
    load_clublab_env()
    origin = (os.environ.get("CLUBLAB_ORIGIN") or DEFAULT_ORIGIN).strip()
    token = login_token(origin)
    return ClublabHttpClient(origin, token)


def _require_ok(resp: HttpResponse, path: str) -> Any:
    if resp.status >= 400:
        raise ClublabPullError(resp.status, resp.url, str(resp.body)[:200])
    return resp.body


def _fetch_facility(client: ClublabHttpClient, facility_id: str, name: str) -> tuple[dict[str, Any], list[str]]:
    stripped_all: list[str] = []

    dash_raw = _require_ok(client.get("/api/v1/crm/dashboard/summary", facility_id=facility_id), "crm dashboard")
    dash = _drop_keys(dash_raw if isinstance(dash_raw, dict) else {}, CRM_DASHBOARD_DROP)
    dash, s = sanitize_tree(dash)
    stripped_all.extend(s)

    reports_raw = _require_ok(client.get("/api/v1/crm/reports/summary", facility_id=facility_id), "crm reports")
    reports, s = sanitize_tree(reports_raw)
    stripped_all.extend(s)

    segments_raw = _require_ok(client.get("/api/v1/crm/segments", facility_id=facility_id), "crm segments")
    segments, s = sanitize_tree(segments_raw if isinstance(segments_raw, list) else [])
    stripped_all.extend(s)

    order_raw = _require_ok(client.get("/api/v1/orderme/orders/summary", facility_id=facility_id), "orderme")
    order_doc = order_raw if isinstance(order_raw, dict) else {"products": order_raw}
    products = order_doc.get("products") if isinstance(order_doc, dict) else order_doc
    products, s = sanitize_tree(products if isinstance(products, list) else [])
    stripped_all.extend(s)

    fit_summary_raw = _require_ok(client.get("/api/v1/fitme/summary", facility_id=facility_id), "fitme summary")
    fit_summary, s = sanitize_tree(fit_summary_raw)
    stripped_all.extend(s)

    fit_equip_raw = _require_ok(client.get("/api/v1/fitme/equipment/top", facility_id=facility_id), "fitme equip")
    fit_equip, s = sanitize_tree(fit_equip_raw if isinstance(fit_equip_raw, list) else [])
    stripped_all.extend(s)

    cost_raw = _require_ok(client.get("/api/v1/costme/catalogue", facility_id=facility_id), "costme")
    cost_rows, s = sanitize_tree(cost_raw if isinstance(cost_raw, list) else [])
    stripped_all.extend(s)

    coach_sess_raw = _require_ok(
        client.get("/api/v1/Reports/session-summary", facility_id=facility_id), "coachme sessions"
    )
    coach_sess, s = sanitize_tree(coach_sess_raw)
    stripped_all.extend(s)

    coach_tags_raw = _require_ok(
        client.get("/api/v1/Reports/tag-frequency", facility_id=facility_id), "coachme tags"
    )
    coach_tags, s = sanitize_tree(coach_tags_raw if isinstance(coach_tags_raw, list) else coach_tags_raw)
    stripped_all.extend(s)

    timeline = None
    try:
        tl_resp = client.get("/api/v1/fitme/timeline", facility_id=facility_id)
        if tl_resp.status < 400:
            timeline, s = sanitize_tree(tl_resp.body)
            stripped_all.extend(s)
    except ClublabPullError:
        timeline = None

    row: dict[str, Any] = {
        "id": facility_id,
        "name": name,
        "crm": {"dashboard": dash, "reports": reports, "segments": segments},
        "orderme": {"products": products},
        "fitme": {"summary": fit_summary, "equipment": fit_equip},
        "costme": {"catalogue": cost_rows},
        "coachme": {"sessionSummary": coach_sess, "tagFrequency": coach_tags},
    }
    if timeline is not None:
        row["fitme"]["timeline"] = timeline
    return row, stripped_all


def _compute_totals(facilities: list[dict[str, Any]]) -> dict[str, Any]:
    crm_revenue = 0
    order_count = 0
    fitme_completed = 0
    costme_skus = 0
    coach_sessions = 0
    for fac in facilities:
        reports = (fac.get("crm") or {}).get("reports") or {}
        rev = reports.get("revenue") if isinstance(reports, dict) else {}
        if isinstance(rev, dict):
            crm_revenue += int(rev.get("total") or 0)
        products = (fac.get("orderme") or {}).get("products") or []
        if isinstance(products, list):
            order_count += sum(int(p.get("orderCount") or 0) for p in products if isinstance(p, dict))
        fit_summary = (fac.get("fitme") or {}).get("summary") or {}
        if isinstance(fit_summary, dict):
            fitme_completed += int(fit_summary.get("completed") or 0)
        catalogue = (fac.get("costme") or {}).get("catalogue") or []
        if isinstance(catalogue, list):
            costme_skus += len(catalogue)
        sess = (fac.get("coachme") or {}).get("sessionSummary") or {}
        if isinstance(sess, dict):
            coach_sessions += int(sess.get("totalSessions") or sess.get("sessionCount") or sess.get("count") or 0)
    return {
        "facilityCount": len(facilities),
        "crmRevenueTotal": crm_revenue,
        "ordermeOrderCount": order_count,
        "fitmeCompleted": fitme_completed,
        "costmeSkuCount": costme_skus,
        "coachmeSessionCount": coach_sessions,
    }


def build_snapshot(client: ClublabHttpClient) -> tuple[dict[str, Any], list[str]]:
    fac_resp = _require_ok(client.get("/api/v1/facilities"), "facilities")
    facilities_raw = fac_resp if isinstance(fac_resp, list) else []
    stripped_all: list[str] = []
    facility_rows: list[dict[str, Any]] = []
    for item in facilities_raw:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("id") or item.get("facilityId") or "")
        name = str(item.get("name") or fid)
        if not fid:
            continue
        row, stripped = _fetch_facility(client, fid, name)
        stripped_all.extend(stripped)
        facility_rows.append(row)
    snapshot = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "facilities": facility_rows,
        "totals": _compute_totals(facility_rows),
    }
    snapshot, more = sanitize_tree(snapshot)
    stripped_all.extend(more)
    return snapshot, stripped_all


def write_snapshot_files(snapshot: dict[str, Any], sanitized_keys: list[str]) -> None:
    atomic_write(SNAPSHOT_NAME, snapshot)
    meta = {
        "schema": "campaign-os/clublab-snapshot-meta/v1",
        "generated_at": snapshot.get("generated_at") or utc_now_iso(),
        "sanitized_keys": sorted(set(sanitized_keys)),
    }
    atomic_write(META_NAME, meta)


def counts_summary(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Counts-only per facility for handoff evidence."""
    out: list[dict[str, Any]] = []
    for fac in snapshot.get("facilities") or []:
        if not isinstance(fac, dict):
            continue
        dash = ((fac.get("crm") or {}).get("dashboard") or {}) if isinstance(fac.get("crm"), dict) else {}
        products = (fac.get("orderme") or {}).get("products") or []
        out.append(
            {
                "facility_id": fac.get("id"),
                "facility_name": fac.get("name"),
                "crm_active_total": dash.get("activeTotal") if isinstance(dash, dict) else None,
                "crm_client_count": ((fac.get("crm") or {}).get("reports") or {}).get("clientCount")
                if isinstance(fac.get("crm"), dict)
                else None,
                "orderme_product_rows": len(products) if isinstance(products, list) else 0,
                "fitme_completed": ((fac.get("fitme") or {}).get("summary") or {}).get("completed"),
                "costme_skus": len(((fac.get("costme") or {}).get("catalogue") or [])),
                "coachme_sessions": ((fac.get("coachme") or {}).get("sessionSummary") or {}).get("totalSessions")
                or ((fac.get("coachme") or {}).get("sessionSummary") or {}).get("sessionCount"),
            }
        )
    return out


def run() -> dict[str, Any]:
    """Pull ClubLab stats and write clublab-snapshot.json under DATA_DIR."""
    try:
        client = _build_client()
        snapshot, stripped = build_snapshot(client)
        write_snapshot_files(snapshot, stripped)
        n = len(snapshot.get("facilities") or [])
        return {
            "ok": True,
            "rows": n,
            "sanitized_keys": len(set(stripped)),
            "totals": snapshot.get("totals"),
        }
    except ClublabPullError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "http_status": exc.status,
            "endpoint": exc.url,
            "rows": 0,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": describe_exception(exc), "rows": 0}


def set_http_client_factory(factory: Callable[[], Any] | None) -> None:
    global _http_client_factory
    _http_client_factory = factory
