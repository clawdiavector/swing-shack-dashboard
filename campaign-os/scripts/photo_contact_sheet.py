"""Contact sheet of the photos on the photo map, so a person (or Claude) can look at them
before approving. Titles come from the stock line, filenames from SKU naming.

    python campaign-os/scripts/photo_contact_sheet.py --brand stick --out sheet.png [--status needs-check]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

from _lib import photo_map as pm  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", default="needs-check")
    ap.add_argument("--images")
    ap.add_argument("--cols", type=int, default=6)
    a = ap.parse_args()

    images = Path(a.images) if a.images else pm.images_dir(a.brand)
    ents = [e for e in pm.load(a.brand) if not a.status or e["status"] == a.status]
    ents = [e for e in ents if e.get("viewable", True) and (images / e["file"]).exists()]
    if not ents:
        print("Nothing to show.")
        return 1
    cell, cols = 260, a.cols
    rows = (len(ents) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 46)), "white")
    d = ImageDraw.Draw(sheet)
    for i, e in enumerate(ents):
        im = Image.open(images / e["file"]).convert("RGBA")
        bg = Image.new("RGBA", im.size, (240, 240, 240, 255))
        bg.alpha_composite(im)
        im = bg.convert("RGB")
        im.thumbnail((cell - 8, cell - 8))
        x, y = (i % cols) * cell, (i // cols) * (cell + 46)
        sheet.paste(im, (x + 4, y + 4))
        flag = "" if e.get("exact_build", True) else "  [standard image]"
        d.text((x + 4, y + cell - 2), e["product"][:40], fill="black")
        d.text((x + 4, y + cell + 10), (Path(e["file"]).name + flag)[:44], fill=(90, 90, 90))
    sheet.save(a.out)
    print(f"{len(ents)} photo(s) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
