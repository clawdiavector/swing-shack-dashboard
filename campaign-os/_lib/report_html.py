"""HTML renderer for the weekly marketing report.

Lives in its own module so tests can import it without triggering the
`os.makedirs('/data')` call that fires at app.py import time. The app
calls into here via `_render_weekly_report_html` (defined below) which
matches the signature expected by `app.py::weekly_report_export`.

Self-contained output: inlines CSS, no external fonts/JS/images. Same
input data the markdown renderer consumed so the two views never drift.
"""
from typing import Any, Dict, List


def _esc_html(s: Any) -> str:
    """Minimal HTML escape. Uses stdlib html.escape with quote=False so
    we don't over-escape apostrophes (they're fine inside text)."""
    import html as _html
    return _html.escape(str(s), quote=False)


def render_weekly_report_html(data: Dict[str, Any], md_lines: List[str], brand: str = "") -> str:
    """Render the weekly report as a self-contained HTML page.

    See module docstring for context. Brand-coloured badges for the
    three claim buckets (working/not/look_at) match the SPA palette.
    Attribution claims get a star so the CMO revenue-source bands are
    visually distinct from generic SEO/IG ones.
    """
    interp = data.get("interpretation") or {}
    working = interp.get("whats_working", [])
    not_working = interp.get("whats_not", [])
    look_at = interp.get("look_at", [])
    headline_take = interp.get("headline_take", "")
    sources = interp.get("sources_used", [])

    # Tiny inline CSS, scoped under .wr-* to avoid collisions if pasted
    # into another page. Dark theme matches the SPA so brand consistency.
    css = """
    *{box-sizing:border-box}body{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#0c0d10;color:#e8eaed;line-height:1.55}
    .wr-wrap{max-width:980px;margin:0 auto;padding:32px 24px 80px}
    .wr-h1{font-size:28px;font-weight:700;margin:0 0 6px;letter-spacing:-.01em}
    .wr-sub{color:#9aa0a6;font-size:14px;margin-bottom:24px}
    .wr-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:0 0 32px}
    .wr-kpi{background:#16181c;border:1px solid #2a2d33;border-radius:10px;padding:16px}
    .wr-kpi-val{font-size:24px;font-weight:700;color:#c2f64f}
    .wr-kpi-lbl{color:#9aa0a6;font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-top:4px}
    .wr-h2{font-size:18px;font-weight:700;margin:32px 0 12px;display:flex;align-items:center;gap:8px}
    .wr-h2 .wr-dot{width:10px;height:10px;border-radius:50%}
    .wr-section{margin-bottom:32px}
    .wr-claim{background:#16181c;border:1px solid #2a2d33;border-radius:10px;padding:14px 16px;margin-bottom:10px;border-left:3px solid #2a2d33}
    .wr-claim.working{border-left-color:#42b883}
    .wr-claim.not{border-left-color:#ff6b6b}
    .wr-claim.look{border-left-color:#4f8eff}
    .wr-claim.attribution{background:linear-gradient(90deg,#1a1f2e 0%,#16181c 30%);border-left-color:#fbbf24}
    .wr-claim-text{font-size:14px;font-weight:500;margin-bottom:6px}
    .wr-claim-evid{color:#9aa0a6;font-size:12.5px;line-height:1.5}
    .wr-claim-meta{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;font-size:11px}
    .wr-badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
    .wr-badge.cat{background:#1d2025;color:#9aa0a6}
    .wr-badge.src{background:#1d2025;color:#4f8eff}
    .wr-badge.sev{background:#3d1a1a;color:#ff6b6b}
    .wr-badge.star{background:#3d2f1a;color:#fbbf24}
    .wr-headline{background:#16181c;border-left:3px solid #c2f64f;padding:14px 16px;border-radius:10px;margin-bottom:24px;font-style:italic;color:#e8eaed}
    .wr-foot{margin-top:48px;padding-top:24px;border-top:1px solid #2a2d33;color:#9aa0a6;font-size:12px}
    .wr-sources{display:flex;flex-wrap:wrap;gap:6px}
    .wr-src-chip{background:#1d2025;border:1px solid #2a2d33;padding:4px 10px;border-radius:6px;font-size:12px;color:#9aa0a6;font-family:'SF Mono',Menlo,monospace}
    .wr-num{font-size:11px;color:#9aa0a6;margin-left:auto}
    """

    def claim_html(c, kind):
        text = _esc_html(c.get("claim", ""))
        evid = _esc_html(c.get("evidence", ""))
        cat = c.get("category", "")
        src = c.get("source") or ""
        sev = c.get("severity", "")
        is_attribution = (cat == "attribution")
        css_kind = {"working": "working", "not_working": "not", "look_at": "look"}.get(kind, "working")
        badges = []
        if cat:
            badges.append(f'<span class="wr-badge cat">{_esc_html(cat)}</span>')
        if src:
            badges.append(f'<span class="wr-badge src">{_esc_html(src)}</span>')
        if sev:
            sev_label = {"high": "HIGH", "medium": "MED", "low": "low"}.get(sev, _esc_html(sev))
            badges.append(f'<span class="wr-badge sev">{sev_label}</span>')
        if is_attribution:
            badges.append('<span class="wr-badge star">CMO BAND</span>')
        meta_html = '<div class="wr-claim-meta">' + "".join(badges) + '</div>' if badges else ''
        evid_html = f'<div class="wr-claim-evid">{evid}</div>' if evid else ''
        cls = f"wr-claim {css_kind}" + (" attribution" if is_attribution else "")
        return (
            f'<div class="{cls}">'
            f'<div class="wr-claim-text">{text}</div>'
            f'{evid_html}'
            f'{meta_html}'
            f'</div>'
        )

    kpis = data.get("headline_kpis", {})
    kpi_cards = []
    for label, key in [
        ("Published", "published"),
        ("Failed", "failed"),
        ("Win rate", "win_rate_pct"),
        ("Agent runs", "agent_runs"),
        ("Pass rate", "agent_pass_rate_pct"),
    ]:
        v = kpis.get(key)
        if v is None:
            v = "—"
        if isinstance(v, float) and key.endswith("_pct"):
            v = f"{v:.1f}%"
        kpi_cards.append(
            f'<div class="wr-kpi"><div class="wr-kpi-val">{_esc_html(v)}</div>'
            f'<div class="wr-kpi-lbl">{_esc_html(label)}</div></div>'
        )
    kpi_html = '<div class="wr-kpis">' + "".join(kpi_cards) + "</div>"

    working_html = "".join(claim_html(c, "working") for c in working) or '<div class="wr-claim-evid">No working claims this week.</div>'
    not_html = "".join(claim_html(c, "not_working") for c in not_working) or '<div class="wr-claim-evid">No issues this week.</div>'
    look_html = "".join(claim_html(c, "look_at") for c in look_at) or '<div class="wr-claim-evid">No open questions.</div>'

    sources_html = "".join(
        f'<span class="wr-src-chip">{_esc_html(s)}</span>' for s in sources
    ) or '<div class="wr-claim-evid">No sources reported.</div>'

    week_start = (data.get("week_start") or "")[:10]
    week_end = (data.get("week_end") or "")[:10]
    title = f"Weekly Marketing Report · {week_start} → {week_end}"
    if not week_start or not week_end:
        title = "Weekly Marketing Report"

    headline_block = (
        f'<div class="wr-headline">{_esc_html(headline_take)}</div>'
        if headline_take else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc_html(title)}</title>
<style>{css}</style>
</head>
<body>
<div class="wr-wrap">
  <h1 class="wr-h1">{_esc_html(title)}</h1>
  <div class="wr-sub">Brand: <b>{_esc_html(brand or data.get('brand') or 'all')}</b> · Window: {_esc_html(data.get('window_label') or 'rolling 7d')}</div>
  {kpi_html}
  {headline_block}
  <section class="wr-section">
    <h2 class="wr-h2"><span class="wr-dot" style="background:#42b883"></span>What's working <span class="wr-num">{len(working)} claim{'s' if len(working)!=1 else ''}</span></h2>
    {working_html}
  </section>
  <section class="wr-section">
    <h2 class="wr-h2"><span class="wr-dot" style="background:#ff6b6b"></span>What's not working <span class="wr-num">{len(not_working)} issue{'s' if len(not_working)!=1 else ''}</span></h2>
    {not_html}
  </section>
  <section class="wr-section">
    <h2 class="wr-h2"><span class="wr-dot" style="background:#4f8eff"></span>Look at <span class="wr-num">{len(look_at)} question{'s' if len(look_at)!=1 else ''}</span></h2>
    {look_html}
  </section>
  <section class="wr-section">
    <h2 class="wr-h2"><span class="wr-dot" style="background:#9aa0a6"></span>Data sources powering this report <span class="wr-num">{len(sources)} source{'s' if len(sources)!=1 else ''}</span></h2>
    <div class="wr-sources">{sources_html}</div>
  </section>
  <div class="wr-foot">
    Generated by Campaign OS weekly_report · share-link recipients see the same report the team sees.
    Attribution-band claims (yellow border) reflect the conversion-truth engine's ROI confidence classification.
  </div>
</div>
</body>
</html>
"""
