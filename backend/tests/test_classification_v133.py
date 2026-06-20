"""
V1.3.3 — Purpose-first classification tests.

The user's explicit fixture:

  Bathroom Renovations landing page with H2s:
    * Costs
    * Process
    * Budget options
    * FAQs
    * Areas covered

These are SUPPORTING SECTIONS (facets) for the same commercial objective —
not independent sub-topics. With the expanded generic-token vocabulary
and the purpose-first gate, this page MUST classify as Landing.
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.assessment import assess, _is_generic_h2
from audit.extractor import extract


def _build_html(h1, h2s, phrase, url_slug):
    section_text = (
        f"<p>{(phrase + ' is what we deliver. ') * 25}"
        f"Book a call with our team to discuss your project today.</p>"
    )
    sections = "\n".join(f"<h2>{h}</h2>{section_text}" for h in h2s)
    return f"""<!doctype html>
<html><head>
<title>{h1} — Book a Free Quote</title>
<meta name="description" content="{h1} delivered by our team. Book today.">
</head><body><main>
<h1>{h1}</h1>
{sections}
</main></body></html>"""


def _assess(html, url, phrase):
    ex = extract(html, url, 200, 5, "http", url)
    return assess(ex, phrase)


# ---- The user's exact Bathroom Renovations example ----

def test_user_exact_bathroom_renovations_landing():
    """The user's verbatim fixture must classify as Landing.
    H2s: Costs, Process, Budget options, FAQs, Areas covered."""
    html = _build_html(
        h1="Bathroom Renovations",
        h2s=["Costs", "Process", "Budget options", "FAQs", "Areas covered"],
        phrase="bathroom renovations",
        url_slug="bathroom-renovations",
    )
    a = _assess(html, "https://x.test/bathroom-renovations/", "Bathroom Renovations")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


# ---- Generic-H2 + facet-token coverage tests ----

def test_facet_h2_words_filter_correctly():
    """Each of the user's H2s should be filtered as either a generic
    section heading OR purely facet tokens (no sub-topic)."""
    html = _build_html(
        h1="Bathroom Renovations",
        h2s=["Costs", "Process", "Budget options", "FAQs", "Areas covered",
             "Areas we cover", "Coverage area", "Pricing & Packages",
             "Deposit & rates"],
        phrase="bathroom renovations",
        url_slug="bathroom-renovations",
    )
    a = _assess(html, "https://x.test/bathroom-renovations/", "Bathroom Renovations")
    # NONE of these H2s should be detected as sub-topics — all are facets.
    # The page must remain a Landing.
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


def test_purpose_first_overrides_5_sub_topic_h2s():
    """Even with 5 H2s that ARE genuine sub-topics, a purpose-locked
    landing (title + H1 + URL all strongly match + CTA) classifies as
    Landing because the V1.3.3 Hub threshold is ≥6 for purpose-locked
    pages."""
    html = _build_html(
        h1="Local SEO Services",
        h2s=[
            "Google Business Profile Setup",
            "Local Citation Building",
            "Review Management",
            "Map Pack Strategy",
            "Local Schema Markup",
        ],
        phrase="local SEO services",
        url_slug="local-seo-services",
    )
    a = _assess(html, "https://x.test/local-seo-services/", "Local SEO Services")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


def test_hub_still_works_when_subtopics_reach_six():
    """Civion-style page with 6+ truly independent sub-topics still Hub."""
    html = _build_html(
        h1="Spanish Residency Services",
        h2s=[
            "TIE Card Application",
            "NIE Number Application",
            "Empadronamiento Registration",
            "Social Security Application",
            "Digital Certificate Setup",
            "Healthcare Registration",
            "Banking Account Setup",
        ],
        phrase="spanish residency services",
        url_slug="spanish-residency-services",
    )
    a = _assess(html, "https://x.test/spanish-residency-services/",
                "Spanish Residency Services")
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)
