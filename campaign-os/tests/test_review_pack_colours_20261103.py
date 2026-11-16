"""Review pack: every person's words in their own colour (2026-11-03).

A second person on the client side (Yolanda, alongside Chantalle) will comment too.
Christelle promised each person's comment shows in their own colour so it is easy to
see who said what. Colours are kept per pack so a person keeps theirs.

Requirement-Owner: Christelle
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

ITEMS = [{"id": "a", "title": "A post", "kind": "single"}]


class ColourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-colours-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack

        self.rp = review_pack
        self.pid = review_pack.create_pack("Posts", ITEMS)["id"]

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _public(self):
        return self.rp.public_view(self.pid, "tok")

    def test_each_person_gets_a_different_colour_and_keeps_it(self):
        self.rp.add_comment(self.pid, "a", "Chantalle", "One")
        self.rp.add_comment(self.pid, "a", "Yolanda", "Two")
        self.rp.add_comment(self.pid, "a", "Chantalle", "Three")
        cs = self._public()["comments"]["a"]
        self.assertEqual(cs[0]["colour"], cs[2]["colour"])
        self.assertNotEqual(cs[0]["colour"], cs[1]["colour"])
        for c in cs:
            self.assertRegex(c["colour"], r"^#[0-9a-f]{6}$")

    def test_the_same_name_in_any_case_is_one_person(self):
        self.rp.add_comment(self.pid, "a", "Yolanda", "One")
        self.rp.add_comment(self.pid, "a", "yolanda ", "Two")
        cs = self._public()["comments"]["a"]
        self.assertEqual(cs[0]["colour"], cs[1]["colour"])

    def test_decisions_and_uploads_carry_the_persons_colour_too(self):
        self.rp.record_decision(self.pid, "a", "approve", "Yolanda")
        self.rp.add_comment(self.pid, "a", "Yolanda", "Hi")
        v = self._public()
        self.assertEqual(v["decisions"]["a"]["colour"], v["comments"]["a"][0]["colour"])

    def test_a_row_written_before_colours_existed_still_gets_one(self):
        import json
        d = self.rp._pack_dir(self.pid)
        (d / "decisions.json").write_text(json.dumps({"a": {"state": "pending", "by": "Chantalle", "at": "2026-11-03T10:00:00Z", "choice": "C"}}))
        self.assertRegex(self._public()["decisions"]["a"]["colour"], r"^#[0-9a-f]{6}$")

    def test_there_are_enough_colours_that_eight_people_never_share_one(self):
        for i in range(8):
            self.rp.add_comment(self.pid, "a", f"Person {i}", "Hi")
        cs = self._public()["comments"]["a"]
        self.assertEqual(len({c["colour"] for c in cs}), 8)

    def test_the_page_paints_a_comment_in_its_colour(self):
        page = self.rp.render_page(self._public(), token="tok")
        self.assertIn("c.colour", page)


if __name__ == "__main__":
    unittest.main()
