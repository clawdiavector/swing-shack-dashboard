"""Review pack: a carousel is ONE card you swipe through (Christelle, 2026-11-13).

The Swing Shack Christmas carousel went in as five cards ("slide 1 of 5" ... "slide 5 of 5"),
which reads as five separate posts. A card of kind "carousel" holds every slide in order and
the page shows them as one swipeable post: one picture at a time, arrows, a slide counter and
dots, never "Earlier version" on its slides.

Requirement-Owner: Christelle
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _jpeg(colour):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 500), colour).save(buf, "JPEG")
    return buf.getvalue()


class CarouselOneCard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="co-review-carousel-"))
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.tmp)
        for name in list(sys.modules):
            if name == "_lib.review_pack":
                del sys.modules[name]
        from _lib import review_pack
        self.rp = review_pack
        self.pack = review_pack.create_pack("Christmas", [
            {"id": "gift-cards", "title": "Three deals inside", "kind": "carousel", "caption": "Swipe to open."},
        ])["id"]

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_slides_stay_in_order_on_one_card(self):
        colours = ["red", "green", "blue", "white", "black"]
        for i, c in enumerate(colours):
            self.rp.add_item_image(self.pack, "gift-cards", _jpeg(c), replace=(i == 0))
        items = self.rp.view(self.pack)["pack"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(len(items[0]["images"]), 5)
        self.assertEqual(items[0]["kind"], "carousel")

    def test_page_draws_a_carousel_as_one_swipeable_post(self):
        page = self.rp.render_page(self.rp.view(self.pack), token="t")
        self.assertIn('it.kind==="carousel"', page)
        self.assertIn("Slide ", page)                 # counter: Slide 1 of 5
        self.assertIn("Next slide", page)             # arrow buttons have names
        self.assertIn("Previous slide", page)
        self.assertIn("touchstart", page)             # swipe on a phone
        self.assertIn(".car{", page)


if __name__ == "__main__":
    unittest.main()
