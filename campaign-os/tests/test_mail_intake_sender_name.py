"""A filed mail remembers who sent it, as a first name, so the Today page can say where an idea came from."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import mail_intake as mi  # noqa: E402

HERMAN = "herman@example.test"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)


def file(sender):
    return mi.file_message({"message_id": "m1", "from": sender, "subject": "Ideas", "text": "What if"},
                           date(2026, 10, 26))


def test_first_name_comes_from_the_display_name():
    assert file(f"Herman Kriel <{HERMAN}>")["from_name"] == "Herman"


def test_without_a_display_name_the_part_before_the_at_is_used():
    assert file(HERMAN)["from_name"] == "Herman"
