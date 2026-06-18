"""
Backend smoke tests for TSE Page Auditor V1.

We avoid hitting the live network by monkey-patching audit.fetcher.fetch
to return a hand-crafted HTML page. This exercises the full pipeline:
  fetcher (mocked) → extractor → scorer → AuditResult serialisation.

Two HTML fixtures:
  - well-optimised "/local-seo-services/" → expected overall_score ≥ 75
  - poorly-optimised "/random/" → expected overall_score < 35
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from audit import fetcher as fetcher_module
from audit.extractor import extract
from audit.scorer import score_page


GOOD_HTML = """<!doctype html>
<html lang="en"><head>
  <title>Local SEO Services for Small Businesses | Example</title>
  <meta name="description" content="Our local SEO services help small businesses dominate Google Maps and the 3-pack. Free audit, transparent pricing, results in 90 days.">
  <link rel="canonical" href="https://example.test/local-seo-services/">
  <script type="application/ld+json">{
    "@context":"https://schema.org",
    "@type":"Service",
    "name":"Local SEO Services",
    "provider":{"@type":"LocalBusiness","name":"Example"}
  }</script>
  <script type="application/ld+json">{
    "@context":"https://schema.org",
    "@type":"FAQPage",
    "mainEntity":[{
      "@type":"Question",
      "name":"What are local SEO services?",
      "acceptedAnswer":{"@type":"Answer","text":"Local SEO services optimise your business for local search."}
    }]
  }</script>
</head><body>
  <main>
    <h1>Local SEO Services</h1>
    <p>Our local SEO services are designed to grow small businesses through better visibility in local search results. We combine local SEO services with conversion-focused web design.</p>
    <h2>Why local SEO services matter</h2>
    <p>Local SEO services make sure your business shows up when nearby customers search.</p>
    <h2>What our local SEO company delivers</h2>
    <p>Our local SEO company has worked with hundreds of small businesses. As a leading local SEO agency, we focus on measurable wins.</p>
    <h2>FAQ</h2>
    <h3>What are local SEO services?</h3>
    <p>Local SEO services are practices that improve your visibility in local search results.</p>
    <p>{filler}</p>
    <img src="/images/team.jpg" alt="Our local SEO services team in action">
    <img src="/images/dashboard.png" alt="Analytics dashboard">
    <a href="https://example.test/about/">About us</a>
    <a href="https://example.test/blog/local-seo-guide/">Local SEO guide</a>
    <a href="https://example.test/contact/">Local SEO services consultation</a>
    <a href="https://example.test/case-studies/">Case studies</a>
    <a href="https://example.test/services/">All services</a>
    <a href="https://example.test/pricing/">Pricing</a>
    <a href="https://example.test/blog/">Blog</a>
    <a href="https://example.test/blog/local-pack/">Local pack guide</a>
    <a href="https://external.test/">External link</a>
  </main>
</body></html>
""".replace("{filler}", " ".join(["small business growth"] * 200))


BAD_HTML = """<!doctype html>
<html><head>
<title>Random</title>
</head><body>
<p>This is a placeholder page.</p>
</body></html>
"""


@pytest.fixture(autouse=True)
def stub_fetch(monkeypatch):
    """Stub audit.fetcher.fetch so no real network calls happen."""
    def _stub(url, render_js=False):
        if "/local-seo-services/" in url:
            return (GOOD_HTML, url, 200, 42, "http")
        if "/random/" in url:
            return (BAD_HTML, url, 200, 18, "http")
        raise fetcher_module.FetchError(f"unstubbed url: {url}")
    monkeypatch.setattr(fetcher_module, "fetch", _stub)
    # Also patch the import inside server.py at runtime if the test client imports the app.
    yield


def _audit(url, phrase, secondaries=None):
    """End-to-end without spinning up FastAPI: replicate what /api/audit does."""
    html, final_url, status, ms, method = fetcher_module.fetch(url)
    extracted = extract(html, final_url, status, ms, method, url)
    return score_page(extracted, phrase, secondaries or [])


def test_well_optimised_page_scores_high():
    result = _audit(
        "https://example.test/local-seo-services/",
        "local seo services",
        ["local seo company", "local seo agency"],
    )
    assert result.overall_score >= 75, f"expected ≥75, got {result.overall_score}\n{result.area_scores}"
    keys = {s.key for s in result.strengths}
    assert "url_exact" in keys
    assert "h1_exact" in keys
    assert "title_start" in keys
    assert "schema_present" in keys
    assert "schema_faq" in keys
    assert "faq_schema" in keys
    assert "faq_block" in keys
    # Image alt mentioning phrase should appear.
    assert "images_alt_phrase" in keys
    # Internal links recognised + relevant anchor.
    assert "links_count_strong" in keys or "links_count_ok" in keys
    assert "anchor_relevant" in keys


def test_poor_page_scores_low_with_actionable_recs():
    result = _audit("https://example.test/random/", "local seo services")
    assert result.overall_score < 35
    rec_keys = {r.key for r in result.recommendations}
    # Core "missing" recs we expect.
    assert "url_missing" in rec_keys
    assert "title_missing_phrase" in rec_keys or "title_short" in rec_keys
    assert "desc_missing" in rec_keys
    assert "h1_missing" in rec_keys
    # Content thin.
    assert "content_thin" in rec_keys
    # Schema missing.
    assert "schema_missing" in rec_keys
    # No FAQ.
    assert "faq_none" in rec_keys
    # Priority sorting: high priority items must appear before mediums.
    prio_seq = [r.priority for r in result.recommendations]
    rank = {"high": 0, "medium": 1, "low": 2}
    ranks = [rank.get(p, 3) for p in prio_seq]
    assert ranks == sorted(ranks), f"recs not sorted by priority: {prio_seq}"


def test_area_scores_keys_complete():
    result = _audit("https://example.test/local-seo-services/", "local seo services")
    assert set(result.area_scores.keys()) == {
        "url", "meta_title", "meta_description", "h1", "h2",
        "content", "internal_linking", "schema", "images", "faq",
    }
    # Snapshot useful for the UI.
    snap = result.page_snapshot
    assert snap["word_count"] > 0
    assert snap["schema_types"]
    assert snap["faq_count"] >= 1


def test_blank_phrase_returns_guidance_only():
    result = _audit("https://example.test/local-seo-services/", "")
    assert result.overall_score == 0
    assert result.area_scores == {}
    assert len(result.recommendations) == 1
    assert result.recommendations[0].key == "phrase_missing"


def test_bad_url_rejected_by_fetcher():
    with pytest.raises(fetcher_module.FetchError):
        fetcher_module.fetch_http("not-a-url://nope/")


def test_extractor_handles_empty_html():
    extracted = extract("", "https://x.test/", 200, 1, "http", "https://x.test/")
    assert extracted.title == ""
    assert extracted.h1 == []
    assert extracted.word_count == 0
