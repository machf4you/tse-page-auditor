"""
Parse a single page's HTML into a structured ExtractedPage handed to the scorer.

Single dependency: beautifulsoup4 (already lightweight). No JavaScript
execution — that already happened upstream if the user asked for ?render=js.
"""
from __future__ import annotations

import json
import re
from typing import List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import ExtractedPage


_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip()


def _same_host(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()
    except Exception:
        return False


def extract(
    html: str,
    final_url: str,
    status: int,
    fetch_ms: int,
    render_method: str,
    requested_url: str,
) -> ExtractedPage:
    soup = BeautifulSoup(html or "", "html.parser")

    # Title / meta description / canonical.
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

    # Headings.
    def _headings(tag: str) -> List[str]:
        return [
            _norm(h.get_text(" ", strip=True))
            for h in soup.find_all(tag)
            if _norm(h.get_text(" ", strip=True))
        ]

    h1 = _headings("h1")
    h2 = _headings("h2")
    h3 = _headings("h3")

    # Schema (JSON-LD) — extract BEFORE stripping <script> tags below.
    schema_types: List[str] = []
    schema_raw_payloads = []  # keep raw payloads for FAQ extraction
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

    # Body text — strip scripts/styles/nav/footer/header for cleaner density.
    for noisy in soup(["script", "style", "noscript", "template"]):
        noisy.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    body_text = _norm(main.get_text(" ", strip=True))
    word_count = len(body_text.split()) if body_text else 0

    # Links.
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

    # Images.
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

    # FAQ blocks — use pre-decomposition schema payloads, else fall back.
    faq_blocks = _detect_faq_blocks(soup, schema_types, schema_raw_payloads)

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


def _detect_faq_blocks(soup, schema_types, schema_raw_payloads=None) -> List[dict]:
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
        for d in soup.find_all("details"):
            sm = d.find("summary")
            if not sm:
                continue
            q = _norm(sm.get_text(" ", strip=True))
            a = _norm(d.get_text(" ", strip=True))
            if q and "?" in q:
                out.append({"question": q, "answer": a[: len(q)] and a[len(q):].strip() or a})
        for h in soup.find_all(["h2", "h3", "h4"]):
            text = _norm(h.get_text(" ", strip=True))
            if text.endswith("?"):
                sibling = h.find_next_sibling()
                ans = _norm(sibling.get_text(" ", strip=True)) if sibling else ""
                out.append({"question": text, "answer": ans})
    return out
