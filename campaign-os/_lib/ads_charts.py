"""Weekly charts for the ads pages, drawn as inline SVG on the server.

One series per chart, one axis, no library and no script: the page is plain
HTML. Every week carries a hover title over a full-height hit area, the latest
value sits in the caption, and the same numbers are in a table under the
charts, so nothing is only in a tooltip.

Colours come from the page's CSS variables (--series, --line, --mute, --card),
which the page defines for light and dark.
"""
from __future__ import annotations

import datetime as _dt
import html
import math

# Sized so text stays readable at phone width and in a two-up grid on desktop.
W, H = 360, 190
LEFT, RIGHT, TOP, BOTTOM = 44, 10, 16, 24
PLOT_W, PLOT_H = W - LEFT - RIGHT, H - TOP - BOTTOM
MAX_BAR = 24


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def nice_max(value: float) -> float:
    """Smallest of 1, 2, 4, 6 or 10 times a power of ten that covers ``value``,
    so the half-way tick is a clean number."""
    if not value or value <= 0:
        return 2.0
    power = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 4, 6, 10):
        if step * power >= value:
            return round(step * power, 10)
    return round(10 * power, 10)


def week_label(iso: str) -> str:
    d = _dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def _frame(points: list, fmt, integer: bool):
    values = [v for _, v in points if v is not None]
    top = nice_max(max(values, default=0))
    if integer and top < 2:
        top = 2.0  # so the half-way tick of a count is a whole number
    band = PLOT_W / max(len(points), 1)

    def y(v):
        return TOP + PLOT_H - (v / top) * PLOT_H

    parts = []
    for tick in (0, top / 2, top):
        parts.append(f'<line class="grid" x1="{LEFT}" x2="{W - RIGHT}" y1="{y(tick):.1f}" '
                     f'y2="{y(tick):.1f}"/>'
                     f'<text class="tick" x="{LEFT - 6}" y="{y(tick) + 4:.1f}" '
                     f'text-anchor="end">{_e(fmt(tick))}</text>')
    # One label per month, on the first week that starts in it.
    seen = None
    for i, (week, _) in enumerate(points):
        month = week[:7]
        if month != seen and (i == 0 or _dt.date.fromisoformat(week).day <= 7):
            seen = month
            x = LEFT + band * i + band / 2
            if x < W - RIGHT - 12:
                parts.append(f'<text class="tick" x="{x:.1f}" y="{H - 7}" text-anchor="middle">'
                             f'{_e(_dt.date.fromisoformat(week).strftime("%b"))}</text>')
    return parts, band, y


def _hits(points: list, band: float, fmt, noun: str) -> str:
    """A full-height, focusable hit area per week, wider than any mark."""
    out = []
    for i, (week, v) in enumerate(points):
        text = f"Week of {week_label(week)}: " + (fmt(v) if v is not None else f"no {noun}")
        out.append(f'<rect class="hit" tabindex="0" x="{LEFT + band * i:.1f}" y="{TOP}" '
                   f'width="{band:.1f}" height="{PLOT_H}"><title>{_e(text)}</title></rect>')
    return "".join(out)


def _svg(label: str, body: list) -> str:
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{_e(label)}">'
            + "".join(body) + '</svg>')


def _summary(title: str, points: list, fmt) -> str:
    values = [(w, v) for w, v in points if v is not None]
    if not values:
        return f"{title}: nothing in this period."
    last_w, last_v = values[-1]
    high_w, high_v = max(values, key=lambda p: p[1])
    count = f"{len(points)} week{'' if len(points) == 1 else 's'}"
    return (f"{title}, {count}. Latest, week of {week_label(last_w)}: {fmt(last_v)}. "
            f"Highest, week of {week_label(high_w)}: {fmt(high_v)}.")


def columns(title: str, points: list, fmt, *, integer: bool = False, noun: str = "data") -> str:
    """One column per week. ``points`` is [(iso_week_start, value)]."""
    parts, band, y = _frame(points, fmt, integer)
    width = max(min(MAX_BAR, band - 2), 1)
    base = TOP + PLOT_H
    for i, (_, v) in enumerate(points):
        if not v:
            continue
        x = LEFT + band * i + (band - width) / 2
        top = min(y(v), base - 1)
        r = min(4, width / 2, base - top)
        # Rounded at the data end, square on the baseline.
        parts.append(f'<path class="bar" d="M{x:.1f},{base} V{top + r:.1f} '
                     f'Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} H{x + width - r:.1f} '
                     f'Q{x + width:.1f},{top:.1f} {x + width:.1f},{top + r:.1f} V{base} Z"/>')
    parts.append(_hits(points, band, fmt, noun))
    return _svg(_summary(title, points, fmt), parts)


def line(title: str, points: list, fmt, *, noun: str = "data") -> str:
    """A line with gaps where a week has no value, and a dot on any point that
    would otherwise be invisible because both neighbours are missing."""
    parts, band, y = _frame(points, fmt, False)

    def xy(i, v):
        return LEFT + band * i + band / 2, y(v)

    run, isolated, last = [], [], None
    for i, (_, v) in enumerate(list(points) + [(None, None)]):
        if v is not None:
            run.append(xy(i, v))
            last = (i, v)
            continue
        if len(run) == 1:
            isolated.append(run[0])
        elif run:
            d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in run)
            parts.append(f'<path class="ln" d="{d}"/>')
        run = []
    for px, py in isolated:
        parts.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="4"/>')
    if last:
        px, py = xy(*last)
        parts.append(f'<circle class="dot" cx="{px:.1f}" cy="{py:.1f}" r="4"/>')
    parts.append(_hits(points, band, fmt, noun))
    return _svg(_summary(title, points, fmt), parts)


CSS = """
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}
.charts figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 12px 6px}.charts figcaption{font-weight:600;font-size:14px}
.charts figcaption span{display:block;font-weight:400;color:var(--mute);font-size:13px}
.chart{display:block;width:100%;height:auto;margin-top:6px}
.chart .grid{stroke:var(--line);stroke-width:1}.chart .tick{fill:var(--mute);font-size:11px}
.chart .bar{fill:var(--series)}.chart .ln{fill:none;stroke:var(--series);stroke-width:2;
stroke-linejoin:round;stroke-linecap:round}
.chart .dot{fill:var(--series);stroke:var(--card);stroke-width:2}
.chart .hit{fill:var(--ink);fill-opacity:0;outline:none}
.chart .hit:hover,.chart .hit:focus{fill-opacity:.07}
"""
