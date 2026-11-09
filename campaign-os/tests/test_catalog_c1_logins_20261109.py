"""C1 — named logins, roles, and real authors (2026-11-09)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from itsdangerous import URLSafeTimedSerializer

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

WRONG_HEADER = {"X-Actor-Display-Name": "Header Should Lose"}


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
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
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


def _login_shared(client, app_mod):
    return client.post("/login", data={"password": app_mod.SHARED_PASSWORD})


def _login_user(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def test_create_and_authenticate_user(env):
    _, app_mod, tmp_path = env
    from _lib import users

    u = users.create_user("Kyle Test", "kyle@test.example", "admin", ["*"], "secret-pass-1")
    assert u["email"] == "kyle@test.example"
    assert u["role"] == "admin"
    assert "password_hash" not in u
    auth = users.authenticate("kyle@test.example", "secret-pass-1")
    assert auth and auth["name"] == "Kyle Test"
    listed = users.list_users()
    assert len(listed) == 1
    assert "password_hash" not in listed[0]
    assert (tmp_path / "users.json").is_file()


def test_login_with_email_sets_uid_in_session(env):
    client, app_mod, _ = env
    from _lib import users

    users.create_user("Anna Editor", "anna@test.example", "editor", ["stick"], "anna-pass")
    r = _login_user(client, "anna@test.example", "anna-pass")
    assert r.status_code == 200
    cookie = r.headers.get("Set-Cookie") or client.get_cookie("cos_session").value
    if "cos_session=" in str(cookie):
        token = str(cookie).split("cos_session=", 1)[1].split(";", 1)[0]
    else:
        token = client.get_cookie("cos_session").value
    payload = URLSafeTimedSerializer(app_mod.SESSION_SECRET).loads(token)
    assert payload.get("authed") is True
    assert payload.get("uid")


def test_shared_password_login_still_works(env):
    client, app_mod, _ = env
    r = _login_shared(client, app_mod)
    assert r.status_code == 200
    payload = URLSafeTimedSerializer(app_mod.SESSION_SECRET).loads(
        client.get_cookie("cos_session").value
    )
    assert payload == {"authed": True}


def test_signed_in_plan_approve_records_user_name(env):
    client, _, tmp_path = env
    from _lib import users

    users.create_user("Real Anna", "anna-plan@test.example", "editor", ["stick"], "anna-pass")
    _login_user(client, "anna-plan@test.example", "anna-pass")
    _brief(tmp_path, "brf-c1-001", "note:capetowncycletour:2027-03-14")
    plan = client.post(
        "/api/plan/v1/stick/propose", json={"brief_id": "brf-c1-001"}
    ).get_json()["plan"]
    r = client.post(
        f"/api/plan/v1/stick/{plan['plan_id']}/approve",
        headers=WRONG_HEADER,
        json={"actor": "Body Should Lose"},
    )
    assert r.status_code == 200
    got = client.get(f"/api/plan/v1/stick/{plan['plan_id']}").get_json()["plan"]
    assert got["approved_by"] == "Real Anna"


def test_contributor_cannot_approve_gets_plain_403(env):
    client, _, tmp_path = env
    from _lib import users

    users.create_user("Connie", "con@test.example", "contributor", ["stick"], "con-pass")
    _login_user(client, "con@test.example", "con-pass")
    _brief(tmp_path, "brf-c1-002", "note:capetowncycletour:2027-03-14")
    plan = client.post(
        "/api/plan/v1/stick/propose", json={"brief_id": "brf-c1-002"}
    ).get_json()["plan"]
    r = client.post(f"/api/plan/v1/stick/{plan['plan_id']}/approve", json={})
    assert r.status_code == 403
    msg = r.get_json().get("error", "")
    assert "cannot approve" in msg.lower() or "not approve" in msg.lower()
    assert "Christelle" in msg or "Kyle" in msg


def test_approver_can_campaign_approve_but_not_move():
    from _lib import users

    user = {
        "id": "u-approver",
        "name": "Approver",
        "email": "ap@test.example",
        "role": "approver",
        "brands": ["stick"],
        "disabled": False,
    }
    assert users.can(user, "campaign_approve") is True
    assert users.can(user, "move") is False


def test_users_api_admin_only(env):
    client, app_mod, _ = env
    from _lib import users

    users.create_user("Admin", "admin@test.example", "admin", ["*"], "admin-pass")
    users.create_user("Ed", "ed@test.example", "editor", ["stick"], "ed-pass")
    _login_user(client, "ed@test.example", "ed-pass")
    assert client.get("/api/users").status_code == 403
    anon = app_mod.app.test_client(cos_anon=True)
    _login_user(anon, "admin@test.example", "admin-pass")
    j = anon.get("/api/users").get_json()
    assert j["ok"] and len(j["users"]) >= 2


def test_api_me_shapes(env):
    client, app_mod, _ = env
    from _lib import users

    users.create_user("Me User", "me@test.example", "editor", ["stick"], "me-pass")
    anon = app_mod.app.test_client(cos_anon=True)
    assert anon.get("/api/me").status_code == 401
    _login_shared(client, app_mod)
    shared = client.get("/api/me").get_json()
    assert shared["signed_in"] is True and shared["shared"] is True and shared["user"] is None
    named = app_mod.app.test_client(cos_anon=True)
    _login_user(named, "me@test.example", "me-pass")
    j = named.get("/api/me").get_json()
    assert j["signed_in"] is True and j["shared"] is False
    assert j["user"]["name"] == "Me User"
    assert j["user"]["role"] == "editor"
    assert "password" not in json.dumps(j)


def test_bootstrap_admin_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_ADMIN_EMAIL", "bootstrap@test.example")
    monkeypatch.setenv("COS_ADMIN_PASSWORD", "bootstrap-secret")
    sys.modules.pop("_lib.users", None)
    from _lib import users

    users.ensure_bootstrap()
    rows = users.list_users()
    assert len(rows) == 1
    assert rows[0]["email"] == "bootstrap@test.example"
    assert rows[0]["role"] == "admin"
    assert users.authenticate("bootstrap@test.example", "bootstrap-secret")
