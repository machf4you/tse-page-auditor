"""
V1.1 — integration tests for GET /api/audits/{id}/export hitting the
deployed REACT_APP_BACKEND_URL.

Covers contract for md, txt, pdf, invalid format (422), unknown id (404),
and verifies the strip-layout heading filter end-to-end via /api/audit on
https://example.com/.
"""
import os
import re
import requests
import pytest


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://page-scanner-15.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRIMARY = "Example Domain"


@pytest.fixture(scope="module")
def audit_id():
    """Create a fresh audit against https://example.com/ and return its id."""
    r = requests.post(f"{API}/audit", json={
        "url": "https://example.com/",
        "primary_phrase": PRIMARY,
        "secondary_phrases": [],
        "render_js": False,
    }, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"]
    # Sanity-check: heading extraction filter — example.com has H1 "Example Domain"
    assert "Example Domain" in (data.get("page_snapshot", {}).get("h1") or [])
    return data["id"]


class TestExportMarkdown:
    def test_md_contract(self, audit_id):
        r = requests.get(f"{API}/audits/{audit_id}/export", params={"format": "md"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").lower().startswith("text/markdown")
        assert "charset=utf-8" in r.headers.get("content-type", "").lower()
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        m = re.search(r'filename="([^"]+)"', cd)
        assert m, f"Missing filename in CD: {cd}"
        fname = m.group(1)
        assert fname.endswith(".md")
        assert fname.startswith("tse-audit-")
        # 8-char short id at end before extension
        assert re.match(r"tse-audit-[a-z0-9\-]+-[a-f0-9]{8}\.md$", fname), fname

        body = r.text
        assert "# TSE Page Auditor Report" in body
        assert "https://example.com" in body
        assert PRIMARY.lower() in body.lower()
        # Overall score number must appear (0-100)
        assert re.search(r"\b(?:[0-9]|[1-9][0-9]|100)\b", body)
        assert "## Area scores" in body
        # 10 areas — exporter may use snake_case keys or human labels
        AREA_ALIASES = [
            ("url", "URL"),
            ("meta_title", "Meta title"),
            ("meta_description", "Meta description"),
            ("h1", "H1"),
            ("h2", "H2"),
            ("content", "Content"),
            ("internal_linking", "Internal linking"),
            ("schema", "Schema"),
            ("images", "Images"),
            ("faq", "FAQ"),
        ]
        for key, label in AREA_ALIASES:
            assert key in body or label in body, f"Missing area: {key}/{label}"
        # Sections
        assert re.search(r"Strengths", body, re.IGNORECASE)
        assert re.search(r"Weaknesses", body, re.IGNORECASE)
        assert re.search(r"Recommendations", body, re.IGNORECASE)
        assert "## Page basics" in body

    def test_markdown_alias(self, audit_id):
        r = requests.get(f"{API}/audits/{audit_id}/export", params={"format": "markdown"}, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").lower().startswith("text/markdown")


class TestExportText:
    def test_txt_contract(self, audit_id):
        r = requests.get(f"{API}/audits/{audit_id}/export", params={"format": "txt"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").lower().startswith("text/plain")
        assert "charset=utf-8" in r.headers.get("content-type", "").lower()
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        m = re.search(r'filename="([^"]+)"', cd)
        assert m and m.group(1).endswith(".txt")
        # Banner — should appear near the top
        head = r.text.splitlines()[:6]
        joined = "\n".join(head)
        assert "TSE PAGE AUDITOR REPORT" in joined, f"Banner not in head: {joined!r}"


class TestExportPDF:
    def test_pdf_contract(self, audit_id):
        r = requests.get(f"{API}/audits/{audit_id}/export", params={"format": "pdf"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").lower().startswith("application/pdf")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        m = re.search(r'filename="([^"]+)"', cd)
        assert m and m.group(1).endswith(".pdf")
        body = r.content
        assert body[:4] == b"%PDF", f"Bad PDF magic: {body[:8]!r}"
        assert len(body) >= 1000, f"PDF too small: {len(body)} bytes"


class TestExportInvalid:
    def test_unknown_format_returns_422(self, audit_id):
        r = requests.get(f"{API}/audits/{audit_id}/export", params={"format": "docx"}, timeout=15)
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

    def test_unknown_id_returns_404(self):
        r = requests.get(f"{API}/audits/nonexistent-id/export", params={"format": "md"}, timeout=15)
        assert r.status_code == 404, r.text


class TestHeadingFilterLive:
    """End-to-end sanity: example.com still returns Example Domain in h1."""
    def test_example_com_h1(self):
        r = requests.post(f"{API}/audit", json={
            "url": "https://example.com/",
            "primary_phrase": "example domain",
        }, timeout=60)
        assert r.status_code == 200, r.text
        snap = r.json().get("page_snapshot", {})
        assert "Example Domain" in (snap.get("h1") or [])
