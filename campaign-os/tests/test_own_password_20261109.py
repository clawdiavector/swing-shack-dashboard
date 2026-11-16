"""Each person changes only their own password. A sign-in lasts one year."""
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
    (base / "important-dates" / "2027.json").write_text("{}", encoding="utf-8")
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
    sys.modules.pop("_lib.users", None)
    return loaded_app.app.test_client(cos_anon=True), loaded_app, tmp_path


def _login_shared(client, app_mod):
    return client.post("/login", data={"password": app_mod.SHARED_PASSWORD})


def _login_user(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def test_login_cookie_lasts_one_year(env):
    client, _, _ = env
    from _lib import users

    users.create_user("Year", "year@test.example", "editor", ["*"], "year-pass")
    r = _login_user(client, "year@test.example", "year-pass")
    assert "Max-Age=31536000" in (r.headers.get("Set-Cookie") or "")
    me = client.get("/api/me")
    assert me.status_code == 200
    assert "Max-Age=31536000" in (me.headers.get("Set-Cookie") or "")


def test_person_changes_own_password_only(env):
    client, app_mod, _ = env
    from _lib import users

    users.create_user("Guest", "guest@test.example", "contributor", ["*"], "old-pass")
    users.create_user("Herman", "herman@test.example", "editor", ["*"], "herman-pass")
    _login_user(client, "guest@test.example", "old-pass")

    blocked = client.post("/api/users", json={})
    assert blocked.status_code == 403
    other = next(u for u in users.list_users() if u["email"] == "herman@test.example")
    stolen = client.post(f"/api/users/{other['id']}/password", json={"password": "taken"})
    assert stolen.status_code == 403
    assert users.authenticate("herman@test.example", "herman-pass")

    wrong = client.post("/api/me/password", json={"current": "nope", "password": "new-pass"})
    assert wrong.status_code == 400
    assert users.authenticate("guest@test.example", "old-pass")

    changed = client.post("/api/me/password", json={"current": "old-pass", "password": "new-pass"})
    assert changed.status_code == 200, changed.get_json()
    assert changed.get_json() == {"ok": True}
    assert "password" not in json.dumps(changed.get_json())
    assert users.authenticate("guest@test.example", "new-pass")
    assert users.authenticate("guest@test.example", "old-pass") is None

    shared = app_mod.app.test_client(cos_anon=True)
    _login_shared(shared, app_mod)
    no_name = shared.post("/api/me/password", json={"current": "x", "password": "y"})
    assert no_name.status_code == 400
