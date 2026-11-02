"""Mockup kit for the monthly efforts packs (Christelle, 2026-10-29): mockups are art-directed, never a raw
photo with text on it. These pin the helpers and the bugs met while making the December 2026 pack: a rim
light sliced by the cut-out's own edge, art leaking outside a screen it is placed on, pixel lettering with
soft edges, and boards whose text ran off the canvas."""
import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "mockup_kit", ROOT / "plugins/campaign-os/skills/campaign-os-efforts/scripts/mockup_kit.py")
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)


def test_pixel_text_has_hard_pixels_in_one_colour():
    t = kit.pixel_text("HIGH SCORES", 6, (116, 204, 70))
    assert t.mode == "RGBA"
    assert set(t.getchannel("A").getdata()) <= {0, 255}
    assert t.getchannel("A").getbbox() is not None
    r, g, b, _ = t.getpixel(next((x, y) for y in range(t.height) for x in range(t.width) if t.getpixel((x, y))[3]))
    assert (r, g, b) == (116, 204, 70)


def test_perspective_paste_only_changes_the_screen():
    base = Image.new("RGB", (400, 300), (10, 10, 10))
    art = Image.new("RGB", (200, 120), (255, 0, 0))
    quad = [(100, 80), (300, 70), (300, 210), (110, 200)]
    out = kit.perspective_paste(base, art, quad)
    assert out.getpixel((5, 5)) == (10, 10, 10)
    assert out.getpixel((390, 290)) == (10, 10, 10)
    assert out.getpixel((200, 140))[0] > 200


def test_grade_keeps_size_and_mode():
    im = Image.new("RGB", (120, 90), (128, 128, 128))
    out = kit.grade(im)
    assert out.size == im.size and out.mode == "RGB"


def test_grade_recovers_highlights():
    im = Image.new("RGB", (60, 60), (250, 250, 250))
    flat = kit.grade(im, contrast=1.0, sat=1.0, warmth=0.0)
    assert flat.getpixel((30, 30))[1] < 250


def test_padded_piece_has_a_clear_margin():
    piece = Image.new("RGBA", (50, 80), (200, 100, 50, 255))
    p = kit.padded(piece, 20)
    assert p.size == (90, 120)
    assert p.getpixel((0, 0))[3] == 0 and p.getpixel((89, 119))[3] == 0


def test_rim_light_is_never_sliced_by_the_cutout_edge():
    """A figure touching its own edge must be padded first, or its glow ends in a straight line."""
    piece = Image.new("RGBA", (60, 100), (0, 0, 0, 0))
    ImageDraw.Draw(piece).rectangle((10, 0, 50, 99), fill=(255, 255, 255, 255))   # touches top and bottom
    rim = kit.rim(kit.padded(piece, 40), (226, 113, 36))
    a = rim.getchannel("A")
    edge = [a.getpixel((x, 0)) for x in range(a.width)] + [a.getpixel((x, a.height - 1)) for x in range(a.width)]
    assert max(edge) < 20


def test_phone_frame_wraps_a_screen():
    f = kit.phone(Image.new("RGB", (1080, 1350), (0, 61, 84)), "Feed post")
    assert f.mode == "RGBA" and f.width == 420 + 32


def test_board_fits_everything_on_the_canvas(tmp_path):
    out = tmp_path / "board.jpg"
    screens = [(Image.new("RGB", (1080, 1920), (28, 28, 28)), "Story"), (Image.new("RGB", (1080, 1350), (234, 238, 241)), "Feed")]
    b = kit.board("1 · Brand: An effort", "MOCKUP · samples", "A long description " * 12, screens, out)
    assert out.is_file()
    assert b.width >= 1300
    assert b.width >= sum(kit.phone(s, l).width for s, l in screens)


def test_board_command_line(tmp_path):
    a, c = tmp_path / "a.png", tmp_path / "c.png"
    Image.new("RGB", (1080, 1920), (0, 0, 0)).save(a)
    Image.new("RGB", (1080, 1350), (255, 255, 255)).save(c)
    out = tmp_path / "b.jpg"
    rc = kit.main(["board", "--title", "T", "--note", "MOCKUP", "--sub", "S",
                   "--screen", f"{a}=Story", "--screen", f"{c}=Feed", "--out", str(out)])
    assert rc == 0 and out.is_file()
