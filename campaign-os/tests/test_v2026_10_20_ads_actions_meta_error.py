"""When Meta refuses a change, the person sees Meta's reason, not 'Invalid parameter'."""
import io
import json
import urllib.error
from unittest import mock

import pytest

from _lib import ads_actions as aa


def _http_error(body):
    return urllib.error.HTTPError("https://graph.facebook.com/x", 400, "Bad", {}, io.BytesIO(json.dumps(body).encode()))


def test_user_message_is_shown():
    body = {"error": {"message": "Invalid parameter", "error_user_title": "Budget is too low",
                      "error_user_msg": "Your ad set budget must be more than ZAR36.10."}}
    with mock.patch("urllib.request.urlopen", side_effect=_http_error(body)):
        with pytest.raises(aa.ActionRefused) as e:
            aa.graph_call("POST", "1", "tok", {"end_time": "x"})
    assert "Budget is too low" in str(e.value) and "ZAR36.10" in str(e.value)
    assert "tok" not in str(e.value)


def test_falls_back_to_the_plain_message():
    with mock.patch("urllib.request.urlopen", side_effect=_http_error({"error": {"message": "Nope"}})):
        with pytest.raises(aa.ActionRefused) as e:
            aa.graph_call("GET", "1", "tok")
    assert str(e.value) == "Meta said: Nope"
