"""Small, safe markdown to HTML for WordPress article drafts.

Publish V1 sends the approved article body to WordPress as the post content.
Writer artifacts hold markdown, and WordPress does not render markdown, so a
draft would show literal ## and ** and dead links. This converts the subset the
drafts use: headings (## and ###), paragraphs, bullet and numbered lists, bold,
italic and links. Everything else is escaped text. No raw HTML passes through.

The approved body and its revision lock are unchanged: conversion happens only
when the CMS payload is built.
"""
from __future__ import annotations

import html as _html
import re
from urllib.parse import urljoin, urlparse

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*]\s+(.+)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
_HTML_HINT = re.compile(r"<(p|h[1-6]|ul|ol|li|div|a|strong|em)\b", re.I)


def looks_like_html(text: str) -> bool:
    return bool(_HTML_HINT.search(text or ""))


def _safe_url(url: str, base: str | None) -> str | None:
    url = url.strip()
    if base and not urlparse(url).scheme and not url.startswith("//"):
        url = urljoin(base.rstrip("/") + "/", url.lstrip("/") if url.startswith("/") else url)
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https", "mailto", "tel"):
        return None
    return url


def _inline(text: str, base: str | None) -> str:
    """Escape first, then turn the markdown marks (which survive escaping) into tags."""
    links: list[str] = []

    def stash(m: re.Match) -> str:
        url = _safe_url(_html.unescape(m.group(2)), base)
        label = m.group(1)
        if url is None:
            return label
        links.append(f'<a href="{_html.escape(url, quote=True)}">{_html.escape(label)}</a>')
        return f"\x00{len(links) - 1}\x00"

    text = _LINK.sub(stash, text)
    text = _html.escape(text, quote=False)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], text)


def markdown_to_html(md: str, base_url: str | None = None) -> str:
    """Convert the article markdown. A leading H1 is dropped: WordPress shows the post title itself."""
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    list_kind: str | None = None
    first_block_seen = False

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append("<p>" + _inline(" ".join(p.strip() for p in para), base_url) + "</p>")
            para = []

    def flush_list() -> None:
        nonlocal items, list_kind
        if items and list_kind:
            out.append(f"<{list_kind}>" + "".join(f"<li>{_inline(i, base_url)}</li>" for i in items) + f"</{list_kind}>")
        items, list_kind = [], None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            continue
        h = _HEADING.match(line)
        if h:
            flush_para()
            flush_list()
            level = len(h.group(1))
            if level == 1 and not first_block_seen:
                first_block_seen = True
                continue  # the post title carries it
            level = max(level, 2)
            out.append(f"<h{level}>{_inline(h.group(2), base_url)}</h{level}>")
            first_block_seen = True
            continue
        first_block_seen = True
        b, n = _BULLET.match(line), _NUMBERED.match(line)
        if b or n:
            flush_para()
            kind = "ul" if b else "ol"
            if list_kind and list_kind != kind:
                flush_list()
            list_kind = kind
            items.append((b or n).group(1))
            continue
        flush_list()
        para.append(line)
    flush_para()
    flush_list()
    return "\n".join(out)


def base_from_api(wp_api_base: str | None) -> str | None:
    """https://example.co.za/wp-json/wp/v2 -> https://example.co.za"""
    if not wp_api_base:
        return None
    p = urlparse(wp_api_base)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None
