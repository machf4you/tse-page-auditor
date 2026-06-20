"""
V1.3.4 — "Should this sub-topic become its own landing page?" tests.

The V1.3.3 classifier asked "*could* this H2 become a landing page?"
which mis-counted modifier H2s on focused service pages. The user's
refined principle locks in the right question:

  - SUPPORTING (Landing reinforcers): "Bathroom Renovation Costs",
    "Bathroom Renovation Process", "Bathroom Renovation FAQs" — each
    extends the same service with a facet → must NOT count as a
    sub-topic.
  - INDEPENDENT (Hub reinforcers): "TIE Card Application",
    "NIE Number Application", "Padron Registration",
    "Social Security Number" — each introduces a new named entity
    → MUST count as a sub-topic.

The implementation: an H2 that contains all of the anchor's distinctive
tokens (anchor minus generic decorators) is a facet, regardless of how
many extra modifier words it carries.
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from audit.assessment import (
    _h2_subtopic_tokens,
    _is_h2_anchor_extension,
    assess,
)
from audit.extractor import extract
from audit.scorer import _topic_tokens


# ---- Unit tests on the new gate ----

@pytest.mark.parametrize("h2", [
    "Bathroom Renovation Costs",
    "Bathroom Renovation Process",
    "Bathroom Renovation FAQs",
    "Our Bathroom Renovation Process",
    "How long does a bathroom renovation take",
    "Bathroom Renovation Budget Options",
    "Bathroom Renovation Areas Covered",
])
def test_anchor_extension_h2_is_a_facet(h2):
    """User-spec: H2s that fully extend the 'Bathroom Renovations'
    anchor are facets and MUST NOT count as standalone sub-topics."""
    anchor_tokens = _topic_tokens("Bathroom Renovations")
    assert _is_h2_anchor_extension(_topic_tokens(h2), anchor_tokens), h2
    assert _h2_subtopic_tokens(h2, anchor_tokens) == set(), h2


@pytest.mark.parametrize("h2", [
    "TIE Card Application",
    "NIE Number Application",
    "Padron Registration",
    "Social Security Number",
    "Digital Certificate Setup",
])
def test_independent_service_h2_is_a_subtopic(h2):
    """User-spec: H2s that name new independent services on a Spanish
    bureaucracy hub MUST count as standalone sub-topics."""
    anchor_tokens = _topic_tokens("Spanish Bureaucracy Services")
    assert not _is_h2_anchor_extension(_topic_tokens(h2), anchor_tokens), h2
    assert _h2_subtopic_tokens(h2, anchor_tokens), h2


def test_partial_anchor_overlap_is_not_a_facet():
    """An H2 that overlaps with SOME but not ALL of the distinctive
    anchor tokens is not a facet — e.g. "Public Healthcare System"
    against "Healthcare in Spain" still introduces a Hub-worthy
    sub-topic ({public, system} are new)."""
    anchor_tokens = _topic_tokens("Healthcare in Spain")
    h2 = "Public Healthcare System"
    assert not _is_h2_anchor_extension(_topic_tokens(h2), anchor_tokens)
    assert _h2_subtopic_tokens(h2, anchor_tokens), h2


# ---- End-to-end classification ----

def _build_html(h1, h2s, phrase, url_slug):
    section_text = (
        f"<p>{(phrase + ' delivered by our team. ') * 25}"
        f"Book a call with our team today.</p>"
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


def test_user_spec_landing_with_anchor_extension_h2s():
    """User's verbatim Landing example — every H2 extends the anchor
    'Bathroom Renovations' with a facet."""
    html = _build_html(
        h1="Bathroom Renovations",
        h2s=[
            "Bathroom Renovation Costs",
            "Bathroom Renovation Process",
            "Bathroom Renovation FAQs",
            "Bathroom Renovation Budget Options",
            "Bathroom Renovation Areas Covered",
        ],
        phrase="bathroom renovations",
        url_slug="bathroom-renovations",
    )
    a = _assess(html, "https://x.test/bathroom-renovations/", "Bathroom Renovations")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


def test_user_spec_hub_with_independent_service_h2s():
    """User's verbatim Hub example — every H2 names an independent
    Spanish bureaucracy service. (Padding the user's 4 illustrative
    H2s out to 6 to exceed the V1.3.3 purpose-locked Hub threshold;
    a real bureaucracy hub lists more than 4 services.)"""
    html = _build_html(
        h1="Spanish Bureaucracy Services",
        h2s=[
            "TIE Card Application",
            "NIE Number Application",
            "Padron Registration",
            "Social Security Number",
            "Digital Certificate Setup",
            "Healthcare Registration",
        ],
        phrase="spanish bureaucracy services",
        url_slug="spanish-bureaucracy-services",
    )
    a = _assess(html, "https://x.test/spanish-bureaucracy-services/",
                "Spanish Bureaucracy Services")
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)


def test_assessment_signal_text_uses_should_language():
    """The Hub assessment's sub-topic signal must say 'should be its
    own dedicated landing page', not 'could reasonably become'."""
    html = _build_html(
        h1="Spanish Bureaucracy Services",
        h2s=[
            "TIE Card Application",
            "NIE Number Application",
            "Padron Registration",
            "Social Security Number",
            "Digital Certificate Setup",
            "Healthcare Registration",
            "Banking Account Setup",
        ],
        phrase="spanish bureaucracy services",
        url_slug="spanish-bureaucracy-services",
    )
    a = _assess(html, "https://x.test/spanish-bureaucracy-services/",
                "Spanish Bureaucracy Services")
    assert a.page_type == "hub"
    combined = " ".join(a.page_type_signals).lower()
    assert "should be its own dedicated landing page" in combined
    assert "could reasonably become" not in combined
