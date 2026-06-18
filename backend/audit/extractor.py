"""
Parse a single page's HTML into a structured ExtractedPage handed to the scorer.

Single dependency: beautifulsoup4 (already lightweight). No JavaScript
execution — that already happened upstream if the user asked for ?render=js.

Heading + body extraction is restricted to the MAIN CONTENT scope so that
nav, footer, sidebar, widget and testimonial copy do not leak into the
SEO analysis. Layout blocks are stripped by:
  - semantic tags: <nav>, <footer>, <aside>, top-level <header>
  - class / id heuristics: nav, navigation, menu, footer, sidebar, widget,
    copyright, breadcrumb, testimonial, masthead, site-header, page-footer
The cleaned scope then prefers <main> → <article> → <body>.
"""
from __future__ import annotations

import json
import re
from typing import List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import ExtractedPage


_WS = re.compile(r"\s+")
_LAYOUT_TAGS = ("nav", "footer", "aside")
_LAYOUT_CLASS_PAT = re.compile(
    r"(?:^|[\s_\-])("
    r"nav|navigation|navbar|menu|menubar|"
    r"footer|footers|page-footer|footer-area|site-footer|"
    r"sidebar|sidebars|side-bar|"
    r"widget|widgets|widget-area|"
    r"copyright|copyrights|"
    r"breadcrumb|breadcrumbs|"
    r"testimonial|testimonials|"
    r"masthead|site-header|page-header|header-area|top-bar"
    r")(?:[\s_\-]|$)",
    re.I,
)


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip()


def _same_host(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()
    except Exception:
        return False


def _is_layout_el(el) -> bool:
    """True if element's class or id matches a known layout/widget pattern."""
    if not hasattr(el, "get"):
        return False
    cls_val = el.get("class") or []
    cls = " ".join(cls_val) if isinstance(cls_val, list) else str(cls_val)
    eid = str(el.get("id") or "")
    return bool(_LAYOUT_CLASS_PAT.search(cls)) or bool(_LAYOUT_CLASS_PAT.search(eid))


def _strip_layout(soup: BeautifulSoup) -> None:
    """Remove navigation / footer / sidebar / widget blocks in place."""
    # 1. Semantic layout tags.
    for layout in soup(list(_LAYOUT_TAGS)):
        layout.decompose()
    # 2. Top-level <header> = site masthead. Nested <header> (e.g. inside
    #    <article>) is content and is left alone.
    body_root = soup.body or soup
    for child in list(getattr(body_root, "children", [])):
        if getattr(child, "name", None) == "header":
            child.decompose()
    # 3. Class / id heuristic for sites that do not use semantic tags.
    for el in list(soup.find_all(True)):
        # Skip elements whose ancestor was already decomposed above.
        if el.parent is None or getattr(el, "attrs", None) is None:
            continue
        if _is_layout_el(el):
            el.decompose()


def extract(
    html: str,
    final_url: str,
    status: int,
    fetch_ms: int,
    render_method: str,
    requested_url: str,
) -> ExtractedPage:
    soup = BeautifulSoup(html or "", "html.parser")

    # ---- head metadata (whole document) ----
    title = _norm(soup.title.string) if soup.title and soup.title.string else ""

    desc = ""
    md = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if md and md.get("content"):
        desc = _norm(md.get("content", ""))
    if not desc:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            desc = _norm(og.get("content", ""))

    canonical = ""
    lc = soup.find("link", attrs={"rel": re.compile(r"^canonical$", re.I)})
    if lc and lc.get("href"):
        canonical = _norm(lc.get("href"))

    # ---- schema (JSON-LD) — must run BEFORE we strip <script> tags ----
    schema_types: List[str] = []
    schema_raw_payloads = []
    for s in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            data = json.loads(s.string or s.text or "{}")
        except Exception:
            continue
        schema_raw_payloads.append(data)
        for node in _walk_schema(data):
            t = node.get("@type")
            if isinstance(t, list):
                schema_types.extend(str(x) for x in t)
            elif t:
                schema_types.append(str(t))
    schema_types = list({s for s in schema_types if s})

    # ---- links + images (whole document, BEFORE layout stripping) ----
    # Links and image inventories reflect what a search engine sees on the
    # page; we do not currently exclude footer / nav links from those counts.
    internal, external = [], []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        anchor = _norm(a.get_text(" ", strip=True))
        try:
            absu = urljoin(final_url or requested_url, href)
        except Exception:
            absu = href
        link = {"href": absu, "anchor": anchor}
        if _same_host(absu, final_url or requested_url):
            internal.append(link)
        else:
            external.append(link)

    images = []
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        try:
            absu = urljoin(final_url or requested_url, src)
        except Exception:
            absu = src
        images.append({"src": absu, "alt": _norm(img.get("alt") or "")})

    # ---- clean up + scope content to MAIN AREA only ----
    for noisy in soup(["script", "style", "noscript", "template"]):
        noisy.decompose()
    _strip_layout(soup)
    content_root = soup.find("main") or soup.find("article") or soup.body or soup

    def _headings(tag: str) -> List[str]:
        return [
            _norm(h.get_text(" ", strip=True))
            for h in content_root.find_all(tag)
            if _norm(h.get_text(" ", strip=True))
        ]

    h1 = _headings("h1")
    h2 = _headings("h2")
    h3 = _headings("h3")

    body_text = _norm(content_root.get_text(" ", strip=True))
    word_count = len(body_text.split()) if body_text else 0

    # FAQ blocks — uses the cleaned content_root so footer FAQ widgets do not
    # mask a missing on-page FAQ section.
    faq_blocks = _detect_faq_blocks(content_root, schema_types, schema_raw_payloads)

    return ExtractedPage(
        url=requested_url,
        final_url=final_url or requested_url,
        status_code=status,
        fetch_ms=fetch_ms,
        render_method=render_method,
        title=title,
        meta_description=desc,
        canonical=canonical,
        h1=h1,
        h2=h2,
        h3=h3,
        body_text=body_text,
        word_count=word_count,
        internal_links=internal,
        external_links=external,
        schema_types=schema_types,
        images=images,
        faq_blocks=faq_blocks,
    )


def _walk_schema(node):
    """Yield every dict inside a JSON-LD payload (handles @graph + nested arrays)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_schema(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_schema(v)


def _detect_faq_blocks(scope, schema_types, schema_raw_payloads=None) -> List[dict]:
    out: List[dict] = []
    # 1. JSON-LD FAQPage payload — extract Question/Answer pairs.
    for data in (schema_raw_payloads or []):
        for node in _walk_schema(data):
            if node.get("@type") != "FAQPage":
                continue
            for q in (node.get("mainEntity") or []):
                qn = _norm((q or {}).get("name") or "")
                ans = ""
                accepted = (q or {}).get("acceptedAnswer") or {}
                if isinstance(accepted, dict):
                    ans = _norm(accepted.get("text") or "")
                if qn:
                    out.append({"question": qn, "answer": ans})
    # 2. HTML heuristic — <details>/<summary> or h2/h3 ending with "?".
    if not out:
        for d in scope.find_all("details"):
            sm = d.find("summary")
            if not sm:
                continue
            q = _norm(sm.get_text(" ", strip=True))
            a = _norm(d.get_text(" ", strip=True))
            if q and "?" in q:
                out.append({"question": q, "answer": a[: len(q)] and a[len(q):].strip() or a})
        for h in scope.find_all(["h2", "h3", "h4"]):
            text = _norm(h.get_text(" ", strip=True))
            if text.endswith("?"):
                sibling = h.find_next_sibling()
                ans = _norm(sibling.get_text(" ", strip=True)) if sibling else ""
                out.append({"question": text, "answer": ans})
    return out
