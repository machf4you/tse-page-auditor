"""
V1.3.1 — Landing vs Hub classification refinement tests.

User-reported regression: the V1.3 classifier was mis-classifying focused
landing pages (Bathroom Renovations, Local SEO Services, SEO Services,
NIE & TIE Assistance) as Hubs because they had ≥ 5 H2s.

The new rule is:
  - Strip generic landing-page H2 sections (FAQ / Pricing / Reviews /
    Process / About / Contact / Why Choose Us / Gallery / Benefits etc.).
  - A non-generic H2 introduces a "sub-topic" only when it contains a
    SUBSTANTIVE token that's not in the H1 anchor and not a generic
    decorator word.
  - Hub only if ≥ 4 H2 sections introduce distinct sub-topics.

This file locks in the user's golden examples in both directions.
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from audit.assessment import (
    classify, _is_generic_h2, _h2_subtopic_tokens, _GENERIC_TOKENS
)
from audit.extractor import extract
from audit.scorer import _topic_tokens


# ---------------- helper unit tests ----------------

@pytest.mark.parametrize("h2", [
    "Our process",
    "How it works",
    "Why choose us",
    "Pricing",
    "Pricing & Packages",
    "FAQ",
    "FAQs",
    "Frequently Asked Questions",
    "Reviews",
    "Testimonials",
    "Contact us",
    "About us",
    "Gallery",
    "Case studies",
    "Our team",
    "Benefits",
    "Book a call",
    "Book now",
    "Enquire today",
    "Next steps",
    "Get started",
    "Ready to get started",
    "What our clients say",
])
def test_generic_h2_patterns_recognised(h2):
    assert _is_generic_h2(h2), f"{h2!r} should be detected as generic"


@pytest.mark.parametrize("h2", [
    "TIE Card Application",
    "NIE Number Application",
    "Padron Registration",
    "Public Healthcare",
    "Private Health Insurance",
    "Bathroom Renovations Pricing",  # repeats H1 topic, not generic
])
def test_non_generic_h2_patterns_not_matched(h2):
    # Bathroom Renovations Pricing contains the H1 phrase so the *full*
    # heading isn't a generic standalone — it's content-relevant.
    assert not _is_generic_h2(h2), f"{h2!r} should NOT be flagged generic"


# ---------------- LANDING golden cases (user-specified misclassifications) ----------------

def _audit(html, url, phrase=""):
    return extract(html, url, 200, 5, "http", url)


def _classify(html, url, phrase=""):
    return classify(_audit(html, url, phrase), phrase)


def _build_landing_html(h1, h2s, phrase_used_in_body):
    """Realistic landing-page HTML with generic AND aligned H2s."""
    body_para = (
        f"<p>{(phrase_used_in_body + ' is what we do. ') * 30}"
        f"Book a call with our team today to enquire about our services.</p>"
    )
    h2_html = "\n".join(f"<h2>{h}</h2>{body_para}" for h in h2s)
    return f"""<!doctype html><html><head>
<title>{h1} — Our Service</title>
<meta name="description" content="{h1} for UK clients. Book a call today.">
</head><body>
  <header class="site-header"><nav><a href="/">Home</a></nav></header>
  <main>
    <h1>{h1}</h1>
    {h2_html}
  </main>
  <footer><a href="/contact">Contact</a></footer>
</body></html>"""


def test_landing_bathroom_renovations_with_many_generic_h2s():
    """The user's #1 example — focused service landing page with 5 H2s
    that are all generic landing-page sections."""
    html = _build_landing_html(
        "Bathroom Renovations",
        ["Our process", "Why choose us", "Pricing & packages", "FAQs", "Gallery"],
        "bathroom renovations",
    )
    pt, label, signals = _classify(html, "https://x.test/bathroom-renovations/",
                                   "Bathroom Renovations")
    assert pt == "landing", (label, signals)


def test_landing_local_seo_services_aligned_h2s():
    """Focused service landing — H2s repeat or decorate the H1 topic."""
    html = _build_landing_html(
        "Local SEO Services",
        [
            "What our local SEO services include",
            "How our local SEO services work",
            "Local SEO services pricing",
            "Why choose us for local SEO",
            "FAQs about local SEO services",
        ],
        "local SEO services",
    )
    pt, label, signals = _classify(html, "https://x.test/local-seo-services/",
                                   "Local SEO Services")
    assert pt == "landing", (label, signals)


def test_landing_seo_services_broad_phrase():
    html = _build_landing_html(
        "SEO Services",
        ["Our SEO services process", "Why our SEO services win",
         "SEO services pricing", "Reviews", "Book a call"],
        "SEO services",
    )
    pt, label, signals = _classify(html, "https://x.test/seo-services/", "SEO Services")
    assert pt == "landing", (label, signals)


def test_landing_nie_tie_assistance_combined_service():
    """The trickiest user example — H2s split between NIE and TIE because
    that IS the service. Tokens 'nie' and 'tie' are both already in the
    H1 anchor, so the H2s don't introduce new sub-topics."""
    html = _build_landing_html(
        "NIE & TIE Assistance",
        [
            "What is a NIE number",
            "What is a TIE card",
            "How to apply for your NIE",
            "How to apply for your TIE",
            "Pricing for NIE & TIE assistance",
            "FAQs",
        ],
        "NIE and TIE assistance",
    )
    pt, label, signals = _classify(html, "https://x.test/nie-tie-assistance/",
                                   "NIE & TIE Assistance")
    assert pt == "landing", (label, signals)


def test_landing_with_a_few_vertical_segmentations_stays_landing():
    """A landing page that lists 'X for restaurants', 'X for plumbers',
    'X for dentists' is still a landing — 3 sub-topic H2s is below the
    Hub threshold of 4."""
    html = _build_landing_html(
        "Local SEO Services",
        [
            "Our local SEO services process",  # generic-ish but aligned
            "Local SEO services for restaurants",
            "Local SEO services for plumbers",
            "Local SEO services for dentists",
            "Pricing",
            "FAQs",
        ],
        "local SEO services",
    )
    pt, label, signals = _classify(html, "https://x.test/local-seo-services/",
                                   "Local SEO Services")
    assert pt == "landing", (label, signals)


# ---------------- HUB golden cases (must still classify correctly) ----------------

def test_hub_spanish_residency_services_civion_shape():
    """Civion-style hub: 6 distinct services under one umbrella phrase."""
    html = _build_landing_html(
        "Spanish Residency Services",
        [
            "TIE Card Application",
            "NIE Number Application",
            "Padron Registration",
            "Social Security Registration",
            "Digital Certificate Setup",
            "Tax Residency",
        ],
        "spanish residency services",
    )
    pt, label, signals = _classify(html, "https://x.test/spanish-residency-services/",
                                   "Spanish Residency Services")
    assert pt == "hub", (label, signals)


def test_hub_healthcare_in_spain():
    """Different sub-services under a broad topic."""
    html = _build_landing_html(
        "Healthcare in Spain",
        [
            "Public Healthcare System",
            "Private Health Insurance",
            "Emergency Numbers",
            "Pharmacies and Medication",
            "Medical Tourism",
            "Mental Health Services",
        ],
        "healthcare in Spain",
    )
    pt, label, signals = _classify(html, "https://x.test/healthcare-in-spain/",
                                   "Healthcare in Spain")
    assert pt == "hub", (label, signals)


def test_hub_education_support():
    html = _build_landing_html(
        "Education Support",
        [
            "Schools and Colleges",
            "University Applications",
            "Private Tutoring",
            "Special Educational Needs",
            "Language Lessons",
            "Online Learning Platforms",
        ],
        "education support",
    )
    pt, label, signals = _classify(html, "https://x.test/education-support/",
                                   "Education Support")
    assert pt == "hub", (label, signals)


# ---------------- Sub-topic detection unit tests ----------------

def test_subtopic_tokens_strips_generic_decorators():
    anchor_tokens = _topic_tokens("Bathroom Renovations")
    # "Our process" has only generic tokens — no sub-topic.
    assert _h2_subtopic_tokens("Our process", anchor_tokens) == set()
    # "Bathroom Renovations Pricing" — 'pric' is generic, no sub-topic.
    assert _h2_subtopic_tokens("Bathroom Renovations Pricing", anchor_tokens) == set()


def test_subtopic_tokens_detects_genuine_new_topic():
    anchor_tokens = _topic_tokens("Spanish Residency Services")
    # "TIE Card Application" has 3 substantive new tokens.
    new = _h2_subtopic_tokens("TIE Card Application", anchor_tokens)
    assert "tie" in new and "card" in new
