"""
V1.2 contract verification — explicitly mirrors the bullets in the
review_request so they are visible in the pytest report.

These overlap with test_topic_matching.py on purpose: this file is a
contract checklist, not a unit suite.
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.extractor import extract
from audit.scorer import (
    _stem,
    _topic_score,
    _topic_match,
    score_page,
)


# ---------- Helper unit contract ----------

def test_contract_stem_values():
    assert _stem("residency") == "residenc"
    assert _stem("services") == "servic"
    assert _stem("applications") == "applic"
    assert _stem("application") == "applic"


def test_contract_topic_score_user_example_is_100():
    assert _topic_score(
        "Spanish Residency Services",
        "Residency Services For Expats In Spain",
    ) == 100


def test_contract_topic_match_unrelated_is_false():
    assert _topic_match("Spanish Residency Services", "Cheap Bed Sale") is False


# ---------- End-to-end via score_page ----------

_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head>
  <title>Residency Services for Expats In Spain | TSE</title>
  <meta name="description" content="Our team helps UK expats with residency services in Spain — TIE cards, NIE numbers, Padron registration.">
</head><body>
  <main>
    <h1>Residency Services For Expats In Spain</h1>
    <h2>Why our Spanish residency services matter</h2>
    <p>{filler}</p>
    <img src="/team.jpg" alt="{alt}">
    <a href="https://tse.test/about/">About us</a>
    <a href="https://tse.test/contact/">Contact</a>
    <a href="https://tse.test/blog/">Blog</a>
  </main>
</body></html>
"""


def _make_html(filler_phrase, alt):
    filler = (filler_phrase + " ") * 50
    return _HTML_TEMPLATE.format(filler=filler, alt=alt)


def _audit(url, phrase, html):
    ex = extract(html, url, 200, 10, "http", url)
    return score_page(ex, phrase, [])


def test_contract_h1_topic_strength_and_h1_score_ge_80():
    """Bullet: hand-crafted HTML with H1 'Residency Services For Expats In Spain'
    → strengths include h1_topic AND area_scores['h1'] >= 80."""
    html = _make_html(
        "Our residency services for expats in Spain cover TIE cards, NIE numbers and Padron registration.",
        "Our Spanish residency services team helping a client in Madrid",
    )
    result = _audit("https://tse.test/spanish-residency/",
                    "Spanish Residency Services", html)
    keys = {c.key for c in result.strengths}
    assert "h1_topic" in keys, f"Missing h1_topic in strengths={keys}"
    assert result.area_scores["h1"] >= 80, f"h1 score={result.area_scores['h1']}"


def test_contract_url_topic_strength_and_url_score_ge_70():
    """Bullet: URL slug 'residency-services-for-expats-in-spain' →
    strengths include url_topic AND area_scores['url'] >= 70."""
    html = _make_html(
        "Our residency services for expats in Spain cover TIE cards, NIE numbers and Padron registration.",
        "Our Spanish residency services team helping a client in Madrid",
    )
    result = _audit(
        "https://tse.test/residency-services-for-expats-in-spain/",
        "Spanish Residency Services", html,
    )
    keys = {c.key for c in result.strengths}
    assert "url_topic" in keys, f"Missing url_topic in strengths={keys}"
    assert result.area_scores["url"] >= 70, f"url score={result.area_scores['url']}"


def test_contract_image_alt_topical_match_uses_images_alt_phrase():
    """Bullet: image alt 'Helping expats with residency services in Spain'
    + target 'Spanish Residency Services' → strengths include
    images_alt_phrase (the existing key, now also accepting topical matches)."""
    html = _make_html(
        "Our residency services for expats in Spain cover TIE cards, NIE numbers and Padron registration.",
        "Helping expats with residency services in Spain",
    )
    result = _audit("https://tse.test/spanish-residency/",
                    "Spanish Residency Services", html)
    keys = {c.key for c in result.strengths}
    assert "images_alt_phrase" in keys, f"Missing images_alt_phrase in strengths={keys}"


def test_contract_body_topical_does_not_trigger_content_phrase_missing():
    """Bullet: body uses 'residency services in Spain' but never the
    literal 'Spanish residency services' — recommendations must NOT
    contain content_phrase_missing."""
    html = """<!doctype html><html><body><main>
      <h1>Help for expats moving to Spain</h1>
      <h2>What we cover</h2>
      <p>""" + (
        "We offer residency services in Spain including TIE card help, "
        "NIE number applications, Padron registration and social security. "
    ) * 25 + """</p>
    </main></body></html>"""
    result = _audit("https://tse.test/help/",
                    "Spanish Residency Services", html)
    rec_keys = {c.key for c in result.recommendations}
    assert "content_phrase_missing" not in rec_keys, (
        f"content_phrase_missing leaked into recommendations: {rec_keys}"
    )
