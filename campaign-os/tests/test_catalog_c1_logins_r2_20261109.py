"""C1 round 2 — review fixes for named logins (2026-11-09)."""
from __future__ import annotations

import json
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
    (base / "important-dates").mkdir(parents=True, exist_ok=True)
    (base / "important-dates" / "2027.json").write_text(
        json.dumps(
            {
                "dates": [
                    {
                        "event_name": "Cape Town Cycle Tour",
                        "start_date": "2027-03-14",
                        "end_date": "2027-03-14",
                        "event_type": "SA_SPORT",
                        "notes": "B/C-tier Western Cape Sport.",
                        "status": "VERIFIED",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    sys.modules.pop("app", None)
    sys.modules.pop("_lib.users", None)
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


@pytest.fixture()
def env(loaded_app, monkeypatch, tmp_path):
    from _lib import campaign_brief as cb

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cb, "DATA_DIR_DEFAULT", str(tmp_path))
    for mod_name in ("_lib.users",):
        sys.modules.pop(mod_name, None)
    return loaded_app.app.test_client(cos_anon=True), loaded_app, tmp_path


def _brief(tmp_path, brief_id, event_key, day="2027-03-14"):
    d = tmp_path / "briefs" / "stick"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{brief_id}.json").write_text(
        json.dumps(
            {
                "brief_id": brief_id,
                "brand_id": "stick",
                "status": "approved",
                "revision": 1,
                "source_opportunity": {
                    "event_key": event_key,
                    "name": "Cape Town Cycle Tour",
                    "date": day,
                },
            }
        ),
        encoding="utf-8",
    )


def _login_user(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def test_disabled_user_cookie_is_signed_out(env):
    client, _, _ = env
    from _lib import users

    row = users.create_user("Gone", "gone@test.example", "editor", ["stick"], "gone-pass")
    _login_user(client, "gone@test.example", "gone-pass")
    assert client.get("/api/me").status_code == 200
    users.update_user(row["id"], {"disabled": True})
    assert client.get("/api/me").status_code == 401


def test_deleted_user_cookie_is_signed_out(env):
    client, _, tmp_path = env
    from _lib import users

    row = users.create_user("Deleted", "del@test.example", "editor", ["stick"], "del-pass")
    _login_user(client, "del@test.example", "del-pass")
    assert client.get("/api/me").status_code == 200
    path = tmp_path / "users.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["users"] = [u for u in data["users"] if u.get("id") != row["id"]]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert client.get("/api/me").status_code == 401


def test_approver_can_approve_plan_shape_free_range(env):
    client, _, tmp_path = env
    from _lib import users

    users.create_user("Herman", "herm@test.example", "approver", ["stick"], "herm-pass")
    _login_user(client, "herm@test.example", "herm-pass")
    _brief(tmp_path, "brf-c1-r2-003", "note:capetowncycletour:2027-03-14")
    plan = client.post(
        "/api/plan/v1/stick/propose", json={"brief_id": "brf-c1-r2-003"}
    ).get_json()["plan"]
    r = client.post(f"/api/plan/v1/stick/{plan['plan_id']}/approve", json={})
    assert r.status_code == 200, r.get_json()


def test_contributor_is_not_refused_moving_dates(env):
    client, _, tmp_path = env
    from _lib import users

    users.create_user("Connie", "con-move@test.example", "contributor", ["stick"], "con-pass")
    _login_user(client, "con-move@test.example", "con-pass")
    _brief(tmp_path, "brf-c1-r2-move", "note:capetowncycletour:2027-03-14")
    plan = client.post(
        "/api/plan/v1/stick/propose", json={"brief_id": "brf-c1-r2-move"}
    ).get_json()["plan"]
    users.create_user("Real Anna", "anna-r2@test.example", "editor", ["stick"], "anna-pass")
    editor = env[1].app.test_client(cos_anon=True)
    _login_user(editor, "anna-r2@test.example", "anna-pass")
    editor.post(f"/api/plan/v1/stick/{plan['plan_id']}/approve", json={})
    r = client.post(
        f"/api/plan/v1/stick/{plan['plan_id']}/place",
        headers={"X-Actor-Display-Name": "Connie"},
        json={},
    )
    assert r.status_code != 403, r.get_json()

