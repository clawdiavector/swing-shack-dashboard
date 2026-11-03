"""plan_action.py: shows first, changes only with --yes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plan_action.py"
PLAN = {"id": "pln-1", "brand_id": "stick", "status": "approved", "title": "Black Friday",
        "items": [{"id": "itm-1", "due": "2026-11-23", "kind": "post", "title": "Live"}]}


@pytest.fixture()
def mod(monkeypatch):
    spec = importlib.util.spec_from_file_location("plan_action", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    calls = []

    def fake(base, method, path, body=None, headers=None):
        calls.append((method, path, body, headers))
        if method == "GET":
            return 200, {"ok": True, "plan": PLAN}
        return 200, {"ok": True}

    monkeypatch.setattr(m, "call", fake)
    m.calls = calls
    return m


def run(mod, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["plan_action.py", *args])
    return mod.main()


def test_dry_run_changes_nothing(mod, monkeypatch, capsys):
    assert run(mod, monkeypatch, "approve", "--brand", "stick", "--plan", "pln-1") == 0
    assert [c[0] for c in mod.calls] == ["GET"]
    assert "Nothing changed" in capsys.readouterr().out


def test_yes_approves(mod, monkeypatch):
    assert run(mod, monkeypatch, "approve", "--brand", "stick", "--plan", "pln-1", "--yes") == 0
    assert mod.calls[-1][:2] == ("POST", "/api/plan/v1/stick/pln-1/approve")


def test_place_sends_named_person(mod, monkeypatch):
    assert run(mod, monkeypatch, "place", "--brand", "stick", "--plan", "pln-1", "--as", "Christelle", "--yes") == 0
    method, path, _, headers = mod.calls[-1]
    assert (method, path) == ("POST", "/api/plan/v1/stick/pln-1/place")
    assert headers == {"X-Actor-Display-Name": "Christelle"}


def test_place_needs_name(mod, monkeypatch):
    with pytest.raises(SystemExit):
        run(mod, monkeypatch, "place", "--brand", "stick", "--plan", "pln-1", "--yes")


def test_edit_retitles_step(mod, monkeypatch):
    assert run(mod, monkeypatch, "edit", "--brand", "stick", "--plan", "pln-1", "--item", "itm-1",
               "--title", "20% off Psycho Bunny", "--yes") == 0
    method, path, body, _ = mod.calls[-1]
    assert (method, path) == ("PATCH", "/api/plan/v1/stick/pln-1/item/itm-1")
    assert body["title"] == "20% off Psycho Bunny"
