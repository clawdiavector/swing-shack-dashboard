"""shadow_text_post.py: text lands only inside the photo's shadows."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "shadow_text_post.py"
ARGS = ["--top", "POLO SEASON.", "--top-sub", "PSYCHO BUNNY", "--bottom", "BLACK FRIDAY  ·  23–30 NOV"]


def _photo(path: Path, shadows: bool) -> None:
    im = Image.new("RGB", (1080, 1350), (200, 190, 170))
    if shadows:
        d = ImageDraw.Draw(im)
        d.polygon([(250, 0), (1080, 0), (1080, 380)], fill=(40, 38, 35))
        d.polygon([(0, 1080), (0, 1350), (800, 1350)], fill=(40, 38, 35))
    im.save(path)


def _run(src: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(src), str(out), *ARGS],
                          capture_output=True, text=True)


def test_text_is_drawn_inside_the_shadows(tmp_path):
    src, out = tmp_path / "in.png", tmp_path / "out.png"
    _photo(src, shadows=True)
    r = _run(src, out)
    assert r.returncode == 0, r.stderr
    before, after = Image.open(src).convert("RGB"), Image.open(out).convert("RGB")
    assert after.size == before.size
    # the lit middle of the photo is untouched
    for xy in ((540, 675), (300, 600), (900, 900)):
        assert after.getpixel(xy) == before.getpixel(xy)
    # mint and white text appear in the top-right and bottom-left corners
    top = after.crop((500, 0, 1080, 200)).getcolors(1 << 20)
    bottom = after.crop((0, 1150, 700, 1350)).getcolors(1 << 20)
    assert any(c[1][1] > 200 and c[1][0] < 120 for c in top)       # mint
    assert any(min(c[1]) > 230 for c in bottom)                     # white


def test_refuses_a_photo_without_shadows(tmp_path):
    src, out = tmp_path / "in.png", tmp_path / "out.png"
    _photo(src, shadows=False)
    r = _run(src, out)
    assert r.returncode != 0
    assert "does not fit" in (r.stderr + r.stdout)
    assert not out.exists()
