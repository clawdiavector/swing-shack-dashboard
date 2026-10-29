"""Tuesday weekly-report share links: https, and the logged-out reader still sees this week's numbers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture(scope="module")
def loaded_app(tmp_path_factory):
    base = tmp_path_factory.mktemp("cosdata")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


def test_a_share_link_reader_gets_the_report_data_and_https_links(loaded_app, monkeypatch):
    monkeypatch.setattr(loaded_app, "COS_JOB_TOKEN", "test-job-token-not-a-secret")
    auth = {"Authorization": "Bearer test-job-token-not-a-secret"}
    seen = {}

    class FakeReport:
        @staticmethod
        def build_v31(bid, fmt="html", as_of=None, cookie=None):
            seen["cookie"] = cookie
            return {"rendered": "<p>report</p>"}

    monkeypatch.setattr(loaded_app, "_wr3", FakeReport)
    anon = loaded_app.app.test_client(cos_anon=True)

    # the link Foreman sends is https even though the proxy hands us http
    r = anon.get("/api/jobs/weekly-report-message?brand=stick", headers=auth,
                 base_url="http://cos.example.com").get_json()
    link = r["links"]["stick"]
    assert link.startswith("https://cos.example.com/weekly-report?brand=stick&share=")

    # opening it without a login still feeds the report's internal data calls a valid session
    path = "/" + link.split("//", 1)[1].split("/", 1)[1]
    assert anon.get(path).status_code == 200
    name, _, token = seen["cookie"].partition("=")
    assert name == loaded_app.SESSION_COOKIE
    assert loaded_app._serializer.loads(token) == {"authed": True}
    # and the reader is not handed that session
    assert "Set-Cookie" not in anon.get(path).headers
