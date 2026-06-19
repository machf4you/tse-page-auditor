"""
V1.3.2 — Landing Precedence gate tests.

The user reported that *Bathroom Renovations*, *SEO Services*,
*Local SEO Services* and *NIE & TIE Assistance* were still being
mis-classified as Hub Pages because they contain detailed supporting
sections that look like sub-topics.

The new rule: once ≥4 sub-topic H2s are detected, Hub classification is
GATED by three signals — if all three pass the gate, the page is a
deep Landing, not a Hub:

  1. Title, H1, URL strongly match the target phrase
     (≥2 of {title≥80, h1≥80, url≥50})
  2. Commercial CTA detected in body copy
  3. Average words per H2 ≥ 150 (content depth, not navigation cards)

The Civion-style hub case (~70 words per H2) and synthetic Healthcare /
Education hubs (no commercial CTA) still classify as Hub.
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.assessment import assess
from audit.extractor import extract


def _build_deep_landing_html(h1, h2s, sub_topic_h2s, phrase):
    """Realistic deep landing page: strong phrase fit on title/H1/URL,
    commercial CTAs, and substantial content per H2 section (~250 words
    each) — i.e. each H2 is a content section, not a navigation card.
    """
    section_words = " ".join([
        f"{phrase} are what we deliver. Our team handles every detail of "
        f"the project from start to finish, and our reputation rests on it. "
        f"We have completed hundreds of {phrase} projects across the UK. "
    ] * 12)  # ~250 words per section
    sections = "\n".join(
        f"<h2>{h}</h2><p>{section_words}</p>"
        for h in (h2s + sub_topic_h2s)
    )
    return f"""<!doctype html>
<html><head>
  <title>{h1} — Book a Free Consultation</title>
  <meta name="description" content="{h1} delivered by our expert team. Book a call today.">
</head>
<body>
  <main>
    <h1>{h1}</h1>
    {sections}
    <p>Book a call with us to discuss your {phrase} project today.</p>
  </main>
</body></html>"""


def _build_hub_html(h1, h2s, phrase):
    """Realistic hub: short, navigation-card-style sections (~50-80 words
    per H2). No commercial CTA on the page itself — the CTAs live on the
    deeper landing pages each H2 links to."""
    section_text = (
        f"Learn more about {h1.lower()} on our dedicated page. "
        f"We can help you with this part of your journey."
    )
    sections = "\n".join(
        f"<h2>{h}</h2><p>{section_text}</p>"
        f"<a href='/{h.lower().replace(' ', '-')}/'>Read more</a>"
        for h in h2s
    )
    return f"""<!doctype html>
<html><head>
  <title>{h1} — Overview</title>
  <meta name="description" content="Overview of {h1}.">
</head>
<body><main>
  <h1>{h1}</h1>
  <p>Below you'll find an overview of the topics we cover.</p>
  {sections}
</main></body></html>"""


def _assess(html, url, phrase):
    ex = extract(html, url, 200, 5, "http", url)
    return assess(ex, phrase)


# ---------------- LANDING precedence tests ----------------

def test_landing_precedence_bathroom_renovations_with_sub_topics():
    """A deep Bathroom Renovations landing with 5 sub-topic H2s
    (Wet Rooms, Walk-in Showers, Heated Floors, Bathroom Tiles, Mirror
    Cabinets) — each H2 is a substantial content section, not a link
    to a deeper page. Must classify as Landing."""
    html = _build_deep_landing_html(
        h1="Bathroom Renovations",
        h2s=["Our Process", "Pricing", "FAQs", "Reviews"],
        sub_topic_h2s=[
            "Wet Room Conversions",
            "Walk-in Shower Installations",
            "Heated Floor Systems",
            "Bathroom Tile Selections",
            "Mirror Cabinet Choices",
        ],
        phrase="bathroom renovations",
    )
    a = _assess(html, "https://x.test/bathroom-renovations/", "Bathroom Renovations")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


def test_landing_precedence_seo_services_with_sub_topics():
    html = _build_deep_landing_html(
        h1="SEO Services",
        h2s=["Our Process", "Pricing", "FAQs"],
        sub_topic_h2s=[
            "On-Page SEO Optimisation",
            "Technical SEO Auditing",
            "Backlink Building Campaigns",
            "Content Strategy Development",
            "Keyword Research Sprints",
        ],
        phrase="SEO services",
    )
    a = _assess(html, "https://x.test/seo-services/", "SEO Services")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


def test_landing_precedence_local_seo_services_with_sub_topics():
    html = _build_deep_landing_html(
        h1="Local SEO Services",
        h2s=["Our Process", "Pricing", "Reviews"],
        sub_topic_h2s=[
            "Google Business Profile Optimisation",
            "Local Citation Building",
            "Review Management Programmes",
            "Local Schema Markup Setup",
            "Map Pack Strategy Sessions",
        ],
        phrase="local SEO services",
    )
    a = _assess(html, "https://x.test/local-seo-services/", "Local SEO Services")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


def test_landing_precedence_nie_tie_with_sub_topics():
    html = _build_deep_landing_html(
        h1="NIE & TIE Assistance",
        h2s=["Pricing", "FAQs", "Book a call"],
        sub_topic_h2s=[
            "NIE Number Form Preparation",
            "TIE Card Photo Requirements",
            "Police Station Appointment Booking",
            "Document Translation Support",
            "Apostille Certification Service",
        ],
        phrase="NIE and TIE assistance",
    )
    a = _assess(html, "https://x.test/nie-tie-assistance/", "NIE & TIE Assistance")
    assert a.page_type == "landing", (a.page_type_label, a.page_type_signals)


# ---------------- HUB cases must still classify correctly ----------------

def test_hub_short_sections_no_cta_spanish_residency():
    """Civion-style hub: short navigation-card sections (~70 words each),
    no commercial CTA on the umbrella page."""
    html = _build_hub_html(
        h1="Spanish Residency Services",
        h2s=[
            "TIE Card Application",
            "NIE Number Application",
            "Empadronamiento Registration",
            "Social Security Registration",
            "Digital Certificate Setup",
            "Tax Residency Help",
        ],
        phrase="spanish residency services",
    )
    a = _assess(html, "https://x.test/spanish-residency-services/",
                "Spanish Residency Services")
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)


def test_hub_healthcare_in_spain_short_sections():
    html = _build_hub_html(
        h1="Healthcare in Spain",
        h2s=[
            "Public Healthcare System",
            "Private Health Insurance",
            "Pharmacies and Medication",
            "Emergency Medical Services",
            "Mental Health Resources",
            "Medical Tourism Routes",
        ],
        phrase="healthcare in Spain",
    )
    a = _assess(html, "https://x.test/healthcare-in-spain/", "Healthcare in Spain")
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)


def test_hub_education_support_short_sections():
    html = _build_hub_html(
        h1="Education Support",
        h2s=[
            "Schools and Colleges",
            "University Applications",
            "Private Tutoring Programmes",
            "Special Educational Needs",
            "Language Lessons",
            "Online Learning Platforms",
        ],
        phrase="education support",
    )
    a = _assess(html, "https://x.test/education-support/", "Education Support")
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)


# ---------------- Boundary cases ----------------

def test_landing_with_strong_fit_but_no_cta_falls_to_hub():
    """If a page has strong fit + many sub-topic H2s + LONG sections
    BUT no commercial CTA at all, the user's spec is honoured:
    Hub classification kicks back in (the third condition of the
    precedence gate failed)."""
    html = _build_deep_landing_html(
        h1="Bathroom Renovations",
        h2s=[],  # no generic sections
        sub_topic_h2s=[
            "Wet Room Conversions",
            "Walk-in Shower Installations",
            "Heated Floor Systems",
            "Bathroom Tile Selections",
            "Mirror Cabinet Choices",
        ],
        phrase="bathroom renovations",
    ).replace("Book a call with us", "").replace(
        "Book a Free Consultation", "Overview"
    )
    a = _assess(html, "https://x.test/bathroom-renovations/", "Bathroom Renovations")
    # With no CTA the landing precedence gate fails — hub.
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)


def test_weak_fit_with_many_sub_topics_classifies_as_hub():
    """If phrase fit on title/H1/URL is weak, the landing precedence
    gate fails (strong_anchors < 2). Hub takes over."""
    html = _build_deep_landing_html(
        h1="Bathroom Renovations",
        h2s=["Pricing", "FAQs"],
        sub_topic_h2s=[
            "Wet Room Conversions",
            "Walk-in Shower Installations",
            "Heated Floor Systems",
            "Bathroom Tile Selections",
            "Mirror Cabinet Choices",
        ],
        phrase="bathroom renovations",
    )
    # Audit against a totally unrelated phrase — fit will be weak.
    a = _assess(html, "https://x.test/landscape-design/", "Landscape Design")
    assert a.page_type == "hub", (a.page_type_label, a.page_type_signals)
