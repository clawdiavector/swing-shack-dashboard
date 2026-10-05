"""ClubLab pull job, deny-list, routes, and lab page."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
FIXTURES = HERE / "fixtures" / "clublab"

if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

DENY_PATTERN = re.compile(
    r'"(firstName|lastName|fullName|email|phone|clientDisplayName|reviewText|reviewBody|comments|photo|imageUrl)"',
    re.I,
)


def _load_fixture(name: str):
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        return json.load(fh)


class FixtureClublabClient:
    def __init__(self) -> None:
        self.origin = "https://clublab.test"

    def get(self, path: str, *, facility_id: str | None = None):
        from _lib.jobs.layer2.clublab_pull import HttpResponse

        mapping = {
            "/api/v1/facilities": "facilities.json",
            "/api/v1/crm/dashboard/summary": "crm_dashboard_summary.json",
            "/api/v1/crm/reports/summary": "crm_reports_summary.json",
            "/api/v1/crm/segments": "crm_segments.json",
            "/api/v1/orderme/orders/summary": "orderme_orders_summary.json",
            "/api/v1/fitme/summary": "fitme_summary.json",
            "/api/v1/fitme/equipment/top": "fitme_equipment_top.json",
            "/api/v1/costme/catalogue": "costme_catalogue.json",
            "/api/v1/Reports/session-summary": "coachme_session_summary.json",
            "/api/v1/Reports/tag-frequency": "coachme_tag_frequency.json",
        }
        fname = mapping.get(path)
        body = _load_fixture(fname) if fname else {}
        return HttpResponse(status=200, body=body, url=f"{self.origin}{path}")


@pytest.fixture()
def pull_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CLUBLAB_TOKEN", "fixture-token-not-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs.layer2.clublab_pull"):
            del sys.modules[mod]
    from _lib.jobs.layer2 import clublab_pull

    clublab_pull.set_http_client_factory(lambda: FixtureClublabClient())
    yield tmp_path, clublab_pull
    clublab_pull.set_http_client_factory(None)


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.clublab_pull_routes"):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client()


def test_login_token_reads_data_access_token(monkeypatch):
    monkeypatch.delenv("CLUBLAB_TOKEN", raising=False)
    monkeypatch.setenv("CLUBLAB_EMAIL", "u@example.com")
    monkeypatch.setenv("CLUBLAB_PASSWORD", "pw-not-logged")
    for mod in list(sys.modules):
        if mod.startswith("_lib.jobs.layer2.clublab_pull"):
            del sys.modules[mod]
    from _lib.jobs.layer2 import clublab_pull

    body = json.dumps({"success": True, "data": {"accessToken": "abc"}}).encode("utf-8")

    class _FakeResp:
        status = 200

        def read(self) -> bytes:
            return body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch.object(clublab_pull, "urlopen", return_value=_FakeResp()):
        assert clublab_pull.login_token("https://clublab.test") == "abc"


def test_run_returns_rows(pull_env):
    tmp_path, clublab_pull = pull_env
    result = clublab_pull.run()
    assert result["ok"] is True
    assert result["rows"] == 1
    assert (tmp_path / "clublab-snapshot.json").is_file()


def test_run_writes_snapshot(pull_env):
    tmp_path, clublab_pull = pull_env
    clublab_pull.run()
    snap_path = tmp_path / "clublab-snapshot.json"
    assert snap_path.is_file()
    doc = json.loads(snap_path.read_text(encoding="utf-8"))
    assert doc["schema"] == clublab_pull.SCHEMA
    assert len(doc["facilities"]) == 1


def test_deny_list_strips_identity_fields(pull_env):
    tmp_path, clublab_pull = pull_env
    clublab_pull.run()
    raw = (tmp_path / "clublab-snapshot.json").read_text(encoding="utf-8")
    assert not DENY_PATTERN.search(raw)
    meta = json.loads((tmp_path / "clublab-snapshot.meta.json").read_text(encoding="utf-8"))
    assert meta.get("sanitized_keys")


def test_page_renders(app_client):
    r = app_client.get("/clublab-pull")
    assert r.status_code == 200
    assert b"<title>ClubLab pull" in r.data


def test_api_returns_snapshot(pull_env):
    tmp_path, clublab_pull = pull_env
    clublab_pull.run()
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    r = app_module.app.test_client().get("/api/clublab-snapshot")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["snapshot"]["schema"] == "campaign-os/clublab-snapshot/v1"
