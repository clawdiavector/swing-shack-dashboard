"""Campaign OS shared pytest auth fixture (t25).

Scope (master plan t25_scope): human session cookie only, via a real
Flask test-client POST /login. Job-token header auth for scheduled
job endpoints is NOT covered here -- those get contract tests in t31.

Why this patches Flask.test_client instead of only exposing a fixture:
122 of 138 campaign-os test files are unittest.TestCase subclasses, and
pytest cannot inject fixtures into unittest test methods. Patching the
constructor is the only way to reach them without a 3,000-line diff.

Opt out of auto-login with app.test_client(cos_anon=True).

Canonical location: campaign-os/tests/conftest.py (job scoped path).
Root tests/ re-exports this module so both trees get the same patch.
"""
import sys

import pytest

_ORIG_TEST_CLIENT = None


def _cos_app_module(flask_app):
    """The module that defines this Flask app, if it is loaded."""
    return sys.modules.get(flask_app.import_name) or sys.modules.get("app")


def cos_login(client, flask_app):
    """Log a Flask test client in. Returns the login response, or None if
    this app has no /login (not the campaign-os app)."""
    app_mod = _cos_app_module(flask_app)
    pw = getattr(app_mod, "SHARED_PASSWORD", None) if app_mod else None
    if not pw:
        return None
    return client.post("/login", data={"password": pw})


def pytest_configure(config):
    global _ORIG_TEST_CLIENT
    import flask

    # Idempotent across two module identities (campaign-os/tests/conftest.py
    # and the importlib copy loaded by tests/conftest.py). A process-level
    # attribute beats a per-module global — otherwise cos_anon is swallowed
    # by a double wrap when both trees are collected together.
    if getattr(flask.Flask.test_client, "_cos_auth_patched", False):
        return
    _ORIG_TEST_CLIENT = flask.Flask.test_client

    def test_client(self, *args, cos_anon=False, **kwargs):
        c = _ORIG_TEST_CLIENT(self, *args, **kwargs)
        if cos_anon:
            return c
        if "login_submit" not in self.view_functions:
            return c  # not the campaign-os app; leave alone
        try:
            cos_login(c, self)
        except Exception:
            pass  # a client that cannot log in is the old behaviour
        return c

    test_client._cos_auth_patched = True
    flask.Flask.test_client = test_client
    if hasattr(config, "addinivalue_line"):
        config.addinivalue_line(
            "markers", "cos_anon: test expects an unauthenticated client"
        )


def pytest_unconfigure(config):
    import flask

    global _ORIG_TEST_CLIENT
    if _ORIG_TEST_CLIENT is not None and getattr(
        flask.Flask.test_client, "_cos_auth_patched", False
    ):
        flask.Flask.test_client = _ORIG_TEST_CLIENT
        _ORIG_TEST_CLIENT = None


# ---- named fixtures, for the few pytest-style files --------------------------


@pytest.fixture
def cos_app():
    """The campaign-os Flask app object."""
    from app import app

    return app


@pytest.fixture
def cos_session(cos_app):
    """An authenticated Flask test client (session cookie, POST /login)."""
    return cos_app.test_client()


@pytest.fixture
def cos_anon_client(cos_app):
    """A deliberately unauthenticated client, for 401 assertions."""
    return cos_app.test_client(cos_anon=True)
