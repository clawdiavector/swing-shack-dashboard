"""Weekly stock report: what to push, what is heavy, what is thin, which photos are missing.

    python campaign-os/scripts/stock_pulse_report.py stock.csv --brand swing-shack
    python campaign-os/scripts/stock_pulse_report.py stock.csv --brand swing-shack --save

Dry run by default: reads past snapshots but writes nothing. --save records this
week's snapshot beside the catalog (same as importing through the dashboard).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from _lib import stock_pulse as sp  # noqa: E402


LINES = []


def say(text: str = "") -> None:
    LINES.append(text)
    print(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--out", help="also write the report to this markdown file")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--images", help="folder of product photos (default: the brand's images folder)")
    a = ap.parse_args()

    rows = sp.parse_stock_csv(Path(a.csv).read_text(encoding="utf-8-sig"))
    if a.save:
        sp.save_snapshot(a.brand, rows, a.date)
        snaps = sp.load_snapshots(a.brand)
    else:
        snaps = [s for s in sp.load_snapshots(a.brand) if s["date"] != a.date]
        snaps.append({"date": a.date, "rows": rows})
    results = sp.analyse(snaps)

    images = Path(a.images) if a.images else HERE.parents[1] / "data" / "brand-directory" / a.brand / "images"
    say(f"# {a.brand} stock pulse, {a.date}\n")
    say(f"{len(rows)} stock lines, {len(results)} products, {len(snaps)} weekly snapshot(s) on record.\n")

    pushes = sp.push_list(results)
    say("## Still too long: push these")
    if pushes:
        for r in pushes:
            say(f"- {r['name']}: {r['reason']}. {r['idea']}")
    else:
        say("- None yet." + (" This is the first list, so there is nothing to compare against." if len(snaps) < 2 else ""))

    say("\n## Heavy shelves (deep stock against alert level)")
    for r in sp.heavy_shelf(results):
        say(f"- {r['name']}: {r['reason']}")

    say("\n## Thin: do not push, consider reordering")
    for r in results:
        if r["status"] == "low":
            extra = f" (short: {', '.join(r['thin_variants'])})" if r["thin_variants"] else ""
            say(f"- {r['name']}: {r['reason']}{extra}")

    say("\n## Out of stock (kept out of the feed)")
    for r in results:
        if r["status"] == "out":
            say(f"- {r['name']}")

    say("\n## Left out on purpose (not sold-as-is product)")
    for r in results:
        if r["not_for_feed"]:
            say(f"- {r['name']}: {r['excluded_reason']}")

    say("\n## Check the file")
    for line in sp.data_problems(results, rows):
        say(f"- {line}")

    say("\n## Real photos")
    counts = {"exact": 0, "candidate": 0, "none": 0}
    need = []
    for r in results:
        if r["status"] in ("out", "error") or r["not_for_feed"]:
            continue
        m = sp.match_photos(r["name"], images)
        counts[m["match"]] += 1
        if m["match"] != "exact":
            need.append((r, m))
    say(f"{counts['exact']} products have a photo whose filename carries the full make and model, "
          f"{counts['candidate']} have only a maker-level candidate, {counts['none']} have nothing.\n")
    say("Needing a photo, pushes and heavy shelves first:")
    priority = {"stuck": 0, "still": 1, "heavy": 2}
    need.sort(key=lambda x: (priority.get(x[0]["status"], 3) if not x[0]["deep_shelf"] else 2, -x[0]["qty"]))
    for r, m in need:
        cand = f" (candidates to check by eye: {', '.join(Path(c).name for c in m['candidates'])})" if m["candidates"] else ""
        say(f"- {r['name']} [{r['qty']}]{cand}")
    if a.out:
        Path(a.out).write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
