"""The ads job must find the running app's ingest. Production starts the server with `python app.py`, so the app
module is `__main__`, not `app` (the first version of the cache warm-up only looked for `app` and never ran)."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.layer7 import ads_brief  # noqa: E402


def _mod(with_ingest=True):
    m = types.ModuleType("fake")
    if with_ingest:
        m._v23_ingest_paid_media = lambda *a, **k: {}
    return m


class FindsTheApp(unittest.TestCase):
    def setUp(self):
        self._saved = {k: sys.modules.get(k) for k in ("app", "__main__")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_finds_it_as_main_when_the_server_runs_python_app_py(self):
        main = _mod()
        sys.modules.pop("app", None)
        sys.modules["__main__"] = main
        self.assertIs(ads_brief._app_module(), main)

    def test_finds_it_as_app_when_imported(self):
        app = _mod()
        sys.modules["app"] = app
        sys.modules["__main__"] = _mod(with_ingest=False)
        self.assertIs(ads_brief._app_module(), app)

    def test_none_when_neither_is_the_app(self):
        sys.modules.pop("app", None)
        sys.modules["__main__"] = _mod(with_ingest=False)
        self.assertIsNone(ads_brief._app_module())


if __name__ == "__main__":
    unittest.main()
