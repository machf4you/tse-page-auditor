"""
V1.2 — Topic Matching tests.

Verifies that the deterministic token-overlap scorer treats semantically
equivalent phrases as the same topic, NOT as a partial fail.

User's bug example:
  Target phrase: Spanish Residency Services
  H1:            Residency Services For Expats In Spain
  → human SEO verdict: strong match
  → V1.1 verdict:      h1_partial (warn) — wrong
  → V1.2 verdict:      h1_topic   (pass) — fixed
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from audit.extractor import extract
from audit.scorer import (
    _topic_score,
    _topic_match,
    _topic_tokens,
    _stem,
    score_page,
)


# ---------------- helper unit tests ----------------

def test_stem_strips_common_suffixes():
    assert _stem("residency") == "residenc"
    assert _stem("residencies") == "residenc"
    assert _stem("services") == "servic"
    assert _stem("application") == "applic"
    assert _stem("applications") == "applic"


def test_topic_tokens_normalises_demonyms():
    a = _topic_tokens("Spanish Residency Services")
    b = _topic_tokens("Residency Services For Expats In Spain")
    # Both should contain stem of residenc, servic, span — order independent.
    assert "residenc" in a and "residenc" in b
    assert "servic" in a and "servic" in b
    assert "spain" in a and "spain" in b


def test_topic_score_user_example():
    # User's headline example.
    assert _topic_score(
        "Spanish Residency Services",
        "Residency Services For Expats In Spain",
    ) == 100
    # Variant phrasings from the user's brief.
    assert _topic_score("Spanish Residency Services", "Spanish Residency Help") >= 67
    assert _topic_score("Spanish Residency Services", "Spanish Residency Support") >= 67


def test_topic_score_is_zero_for_unrelated():
    assert _topic_score("Spanish Residency Services", "Cheap Bed Sale") == 0
    assert _topic_score("local SEO services", "Floor-to-ceiling fitted furniture") == 0


def test_topic_match_threshold_is_80():
    # 3/3 tokens covered → 100% → match.
    assert _topic_match("Spanish Residency Services", "Spain residency services")
    # 2/3 tokens covered → 67% → NOT a strong match.
    assert not _topic_match("Spanish Residency Services", "British residency services")


# ---------------- end-to-end via score_page ----------------

_SPANISH_PAGE = """<!doctype html>
<html lang="en"><head>
  <title>Residency Services for Expats In Spain | TSE</title>
  <meta name="description" content="Our team helps UK expats with residency services in Spain — TIE cards, NIE numbers, Padron registration.">
</head><body>
  <main>
    <h1>Residency Services For Expats In Spain</h1>
    <h2>Why our Spanish residency services matter</h2>
    <p>{filler}</p>
    <img src="/team.jpg" alt="Our Spanish residency services team helping a client in Madrid">
    <a href="https://tse.test/about/">About us</a>
    <a href="https://tse.test/contact/">Contact</a>
    <a href="https://tse.test/blog/">Blog</a>
  </main>
</body></html>
""".replace(
    "{filler}",
    " ".join([
        "Our residency services for expats in Spain cover everything you "
        "need to settle in Spain — TIE cards, NIE numbers, Padron "
        "registration and Social Security registration. "
    ] * 50),
)


def _audit(url, phrase, secondaries=None, html=_SPANISH_PAGE):
    ex = extract(html, url, 200, 10, "http", url)
    return score_page(ex, phrase, secondaries or [])


def test_h1_topic_match_promotes_to_pass():
    """H1 'Residency Services For Expats In Spain' must be a topical PASS,
    not a partial warning, for target 'Spanish Residency Services'."""
    result = _audit("https://tse.test/spanish-residency/", "Spanish Residency Services")
    keys = {c.key for c in result.strengths}
    assert "h1_topic" in keys, f"expected h1_topic in strengths; got {keys}"
    # And it must NOT have landed in weaknesses/recommendations as a fail.
    fail_keys = {c.key for c in result.weaknesses}
    assert "h1_unrelated" not in fail_keys
    assert "h1_missing" not in fail_keys
    # H1 area score is at least 80 (topical-strong tier).
    assert result.area_scores["h1"] >= 80


def test_h2_topic_match_counts_for_primary_phrase():
    # H2 = 'Why our Spanish residency services matter' contains the phrase
    # already → h2_phrase. Test the topical fallback explicitly with a
    # variant that lacks the exact substring.
    html = _SPANISH_PAGE.replace(
        "Why our Spanish residency services matter",
        "Residency services for expats in Spain",
    )
    result = _audit("https://tse.test/spanish-residency/",
                    "Spanish Residency Services", html=html)
    s_keys = {c.key for c in result.strengths}
    assert "h2_topic" in s_keys or "h2_phrase" in s_keys
    assert result.area_scores["h2"] >= 60


def test_url_topic_match_promotes_partial_to_pass():
    """URL slug 'residency-services-for-expats-in-spain' for target
    'Spanish Residency Services' is a topical match, not a partial miss."""
    result = _audit(
        "https://tse.test/residency-services-for-expats-in-spain/",
        "Spanish Residency Services",
    )
    keys = {c.key for c in result.strengths}
    assert "url_topic" in keys or "url_exact" in keys or "url_contains" in keys
    assert result.area_scores["url"] >= 70


def test_content_topic_mentions_count_toward_density():
    """Body that says 'residency services in Spain' a few times — without
    ever using the exact 'Spanish residency services' — must still register
    as on-topic content (not a content_phrase_missing fail)."""
    html = """<!doctype html><html><body><main>
      <h1>Help for expats moving to Spain</h1>
      <h2>What we cover</h2>
      <p>""" + (
        "We offer residency services in Spain including TIE card help, "
        "NIE number applications, Padron registration and social security. "
    ) * 25 + """</p>
    </main></body></html>"""
    result = _audit("https://tse.test/help/", "Spanish Residency Services", html=html)
    rec_keys = {c.key for c in result.recommendations}
    # Should NOT fail with content_phrase_missing — body is topically on-message.
    assert "content_phrase_missing" not in rec_keys


def test_image_alt_topic_match_counts():
    """Image alt 'Our Spanish residency services team helping a client in
    Madrid' matches 'Spanish Residency Services' exactly. Add a variant
    image that's topically equivalent but not an exact match."""
    html = _SPANISH_PAGE.replace(
        'alt="Our Spanish residency services team helping a client in Madrid"',
        'alt="Helping expats with residency services in Spain"',
    )
    result = _audit("https://tse.test/spanish-residency/",
                    "Spanish Residency Services", html=html)
    s_keys = {c.key for c in result.strengths}
    assert "images_alt_phrase" in s_keys


# ---------------- regression: existing well-optimised page still passes ----------------

def test_existing_well_optimised_unchanged():
    """The original well-optimised fixture must still score ≥75 — i.e. the
    topic-match tier did not lower scores for already-exact-match pages."""
    from tests.test_page_auditor_v1 import GOOD_HTML
    result = _audit(
        "https://example.test/local-seo-services/",
        "local seo services",
        ["local seo company", "local seo agency"],
        html=GOOD_HTML,
    )
    assert result.overall_score >= 75
