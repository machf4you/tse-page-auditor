"""
Fetch a single live page and hand back its raw HTML + meta.

Default path: synchronous HTTP GET with realistic User-Agent + 10s timeout.
?render=js path: spin up Playwright Chromium (deferred import — only loaded
when needed so the lightweight image stays light).

Returns: (html: str, final_url: str, status_code: int, fetch_ms: int).
"""
from __future__ import annotations

import time
from typing import Tuple

import requests


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 TSE-PageAuditor/1.0"
)


class FetchError(Exception):
    pass


def fetch_http(url: str, timeout: int = 12) -> Tuple[str, str, int, int]:
    t0 = time.monotonic()
    try:
        r = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": _DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.8",
            },
        )
    except requests.exceptions.RequestException as exc:
        raise FetchError(f"Could not fetch {url}: {exc}") from exc
    dt = int((time.monotonic() - t0) * 1000)
    if r.status_code >= 400:
        raise FetchError(
            f"Server returned HTTP {r.status_code} for {url}. "
            "Use ?render=js if this is a SPA that needs browser rendering."
        )
    return (r.text, r.url, r.status_code, dt)


def fetch_js(url: str, timeout: int = 20) -> Tuple[str, str, int, int]:
    """Lazy import — Playwright is only needed when the caller asks for JS rendering."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: WPS433
    except ImportError as exc:
        raise FetchError(
            "Playwright is not installed in this environment. Install with: "
            "pip install playwright && playwright install chromium"
        ) from exc

    t0 = time.monotonic()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_DEFAULT_UA)
            page = ctx.new_page()
            resp = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            status = resp.status if resp else 0
            final_url = page.url
            html = page.content()
            browser.close()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Browser fetch failed for {url}: {exc}") from exc
    dt = int((time.monotonic() - t0) * 1000)
    if status >= 400:
        raise FetchError(f"Browser fetch returned HTTP {status} for {url}.")
    return (html, final_url, status, dt)


def fetch(url: str, render_js: bool = False) -> Tuple[str, str, int, int, str]:
    """Top-level entry. Returns (html, final_url, status, ms, method)."""
    if not url or not url.startswith(("http://", "https://")):
        raise FetchError("URL must include http:// or https://")
    if render_js:
        html, fu, st, ms = fetch_js(url)
        return (html, fu, st, ms, "js")
    html, fu, st, ms = fetch_http(url)
    return (html, fu, st, ms, "http")
