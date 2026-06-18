"""
TSE Page Auditor V1 — End-to-end API tests against the live backend.

Tests the public /api endpoints over REACT_APP_BACKEND_URL:
  - GET /api/                         health
  - POST /api/audit                   happy path + validation errors
  - POST /api/audit                   upsert behaviour on (url, primary_phrase)
  - GET /api/audits                   history list shape + sort + cap
  - GET /api/audits/{id}              fetch + 404
  - DELETE /api/audits/{id}           delete + 404 + post-condition
  - Recommendations sorted by priority high → medium → low
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://page-scanner-15.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Use a real public, very stable URL for live network audits.
TEST_URL = "https://example.com/"
TEST_PHRASE = "example domain"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health ----------
class TestHealth:
    def test_health_root(self, client):
        r = client.get(f"{API}/")
        assert r.status_code == 200
        data = r.json()
        assert data == {"app": "TSE Page Auditor", "status": "ok"}


# ---------- POST /api/audit happy path + shape ----------
class TestAuditPost:
    EXPECTED_AREAS = {
        "url", "meta_title", "meta_description", "h1", "h2",
        "content", "internal_linking", "schema", "images", "faq",
    }

    def test_audit_happy_path_full_shape(self, client):
        payload = {"url": TEST_URL, "primary_phrase": TEST_PHRASE}
        r = client.post(f"{API}/audit", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()

        # Identity
        assert isinstance(d.get("id"), str) and len(d["id"]) > 0
        assert d["url"] == TEST_URL
        assert d["primary_phrase"] == TEST_PHRASE

        # Score and areas
        assert isinstance(d["overall_score"], int)
        assert 0 <= d["overall_score"] <= 100
        assert isinstance(d["area_scores"], dict)
        assert set(d["area_scores"].keys()) == self.EXPECTED_AREAS

        # Check arrays of ScoreCheck objects
        for arr_key in ("strengths", "weaknesses", "recommendations"):
            assert isinstance(d[arr_key], list)
            for c in d[arr_key]:
                assert {"key", "label", "area", "status", "priority"}.issubset(c.keys())

        # Snapshot
        assert isinstance(d["page_snapshot"], dict)
        assert "word_count" in d["page_snapshot"]
        assert "created_at" in d
        # Stash for downstream tests
        pytest.audit_id = d["id"]
        pytest.first_score = d["overall_score"]

    def test_audit_missing_url(self, client):
        r = client.post(f"{API}/audit", json={"primary_phrase": "x"})
        # 422 from pydantic OR 400 from explicit check both acceptable as "validation rejection"
        assert r.status_code in (400, 422), r.text

    def test_audit_empty_url(self, client):
        r = client.post(f"{API}/audit", json={"url": "", "primary_phrase": "x"})
        assert r.status_code == 400
        assert "url" in r.text.lower()

    def test_audit_missing_primary_phrase(self, client):
        r = client.post(f"{API}/audit", json={"url": TEST_URL})
        assert r.status_code in (400, 422)

    def test_audit_empty_primary_phrase(self, client):
        r = client.post(f"{API}/audit", json={"url": TEST_URL, "primary_phrase": ""})
        assert r.status_code == 400
        assert "primary phrase" in r.text.lower()

    def test_audit_bad_url_returns_400_fetcherror(self, client):
        r = client.post(f"{API}/audit", json={"url": "notaurl", "primary_phrase": "x"})
        assert r.status_code == 400
        body = r.text.lower()
        # FetchError raised by fetcher should propagate as 400 with our message
        assert "http://" in body or "https://" in body or "fetch" in body

    def test_recommendations_sorted_by_priority(self, client):
        # Audit a thin URL to ensure recommendations exist
        r = client.post(
            f"{API}/audit",
            json={"url": "https://example.org/", "primary_phrase": "totally unrelated phrase xyz"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        recs = r.json()["recommendations"]
        rank = {"high": 0, "medium": 1, "low": 2}
        ranks = [rank.get(c["priority"], 3) for c in recs]
        assert ranks == sorted(ranks), f"Recommendations not sorted: {[c['priority'] for c in recs]}"


# ---------- Upsert ----------
class TestUpsert:
    def test_upsert_same_url_phrase(self, client):
        payload = {"url": TEST_URL, "primary_phrase": TEST_PHRASE}
        # Count rows matching this pair before
        list1 = client.get(f"{API}/audits").json()
        matches_before = [r for r in list1 if r["url"] == TEST_URL and r["primary_phrase"] == TEST_PHRASE]
        assert len(matches_before) <= 1, "Already more than one row for (url, phrase) before upsert"

        r1 = client.post(f"{API}/audit", json=payload, timeout=60)
        assert r1.status_code == 200
        id1 = r1.json()["id"]
        r2 = client.post(f"{API}/audit", json=payload, timeout=60)
        assert r2.status_code == 200
        id2 = r2.json()["id"]

        # Upsert keeps original id (since _id is keyed by url+phrase and id field is preserved on first insert)
        # The route does $set with new doc which DOES overwrite id field. Either way: only 1 row should remain.
        list2 = client.get(f"{API}/audits").json()
        matches_after = [r for r in list2 if r["url"] == TEST_URL and r["primary_phrase"] == TEST_PHRASE]
        assert len(matches_after) == 1, f"Expected 1 row after upsert, got {len(matches_after)}"

        # The remaining row should match one of the returned ids
        assert matches_after[0]["id"] in (id1, id2)


# ---------- History list ----------
class TestHistoryList:
    def test_list_shape_and_sort(self, client):
        r = client.get(f"{API}/audits")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) <= 100
        # Each row has the expected slim shape
        for row in rows:
            assert set(row.keys()) >= {"id", "url", "primary_phrase", "overall_score", "created_at"}
            assert isinstance(row["overall_score"], int)
        # Sorted newest first
        timestamps = [row["created_at"] for row in rows]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------- Get + Delete one ----------
class TestGetDelete:
    def test_get_existing(self, client):
        # Re-create to guarantee existence
        r = client.post(f"{API}/audit", json={"url": TEST_URL, "primary_phrase": TEST_PHRASE}, timeout=60)
        assert r.status_code == 200
        audit_id = r.json()["id"]

        g = client.get(f"{API}/audits/{audit_id}")
        assert g.status_code == 200, g.text
        d = g.json()
        assert d["id"] == audit_id
        assert "area_scores" in d and "overall_score" in d

    def test_get_unknown_404(self, client):
        g = client.get(f"{API}/audits/does-not-exist-zzz")
        assert g.status_code == 404

    def test_delete_then_404(self, client):
        # Create dedicated audit to delete
        r = client.post(
            f"{API}/audit",
            json={"url": "https://example.org/", "primary_phrase": "delete me test"},
            timeout=60,
        )
        assert r.status_code == 200
        audit_id = r.json()["id"]

        d = client.delete(f"{API}/audits/{audit_id}")
        assert d.status_code == 200
        assert d.json().get("deleted") == audit_id

        g = client.get(f"{API}/audits/{audit_id}")
        assert g.status_code == 404

        # Deleting again → 404
        d2 = client.delete(f"{API}/audits/{audit_id}")
        assert d2.status_code == 404
