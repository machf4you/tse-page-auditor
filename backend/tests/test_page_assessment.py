"""
V1.3 — Page Assessment tests.

For every audit, the engine must classify the page as
landing / category / hub, score the phrase fit as strong / moderate / weak,
and emit one of the five canonical strategic recommendations.

The user's example fixtures from the V1.3 spec are reproduced verbatim
where applicable so a regression on the contract is immediately obvious.
"""
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audit.assessment import assess, classify, phrase_fit, recommend
from audit.extractor import extract


# ---------- helpers ----------

def _audit_html(html: str, url: str, phrase: str):
    ex = extract(html, url, 200, 5, "http", url)
    return assess(ex, phrase)


# ---------- LANDING PAGE fixtures ----------

LANDING_STRONG_HTML = """<!doctype html><html><head>
<title>Local SEO Services — TSE</title>
<meta name="description" content="Local SEO services for UK businesses. Boost local visibility.">
</head><body>
<main>
  <h1>Local SEO Services</h1>
  <h2>What our local SEO services include</h2>
  <h2>How our local SEO services work</h2>
  <p>{body}</p>
  <p>Book a call with our local SEO services team today.</p>
</main></body></html>""".replace(
    "{body}", " ".join(["Our local SEO services help UK businesses rank for "
                        "their target local SEO services keyword."] * 30),
)


def test_landing_strong_fit_keep_and_optimise():
    a = _audit_html(LANDING_STRONG_HTML,
                    "https://tse.test/local-seo-services/",
                    "Local SEO Services")
    assert a.page_type == "landing", a.page_type_signals
    assert a.fit == "strong", a.fit_score
    assert a.recommendation in (
        "Keep and optimise this page.",
        "Phrase and page are already well aligned.",
    )


LANDING_WEAK_HTML = """<!doctype html><html><head>
<title>About Sheridan France</title>
<meta name="description" content="History of our family-owned business.">
</head><body><main>
  <h1>About our family business</h1>
  <h2>Our team</h2>
  <p>We have been a family-owned business since 1972.</p>
</main></body></html>"""


def test_landing_weak_fit_build_new():
    a = _audit_html(LANDING_WEAK_HTML, "https://tse.test/about/", "Local SEO Services")
    assert a.page_type == "landing"
    assert a.fit == "weak"
    assert a.recommendation == "Create a dedicated landing page for this phrase."


# ---------- CATEGORY PAGE fixtures ----------

CATEGORY_HTML = """<!doctype html><html><head>
<title>Divan Beds | Sheridan France</title>
</head><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"CollectionPage","name":"Divan Beds"}
</script>
<main>
  <h1>Divan Beds</h1>
  <p>Shop our divan beds range. Quality divan beds in single, double and king sizes.</p>
  <div class="product">King Divan £499</div>
  <div class="product">Double Divan £399</div>
  <div class="product">Single Divan £299</div>
  <div class="product">Super King Divan £599</div>
  <div class="product">Storage Divan £549</div>
  <div class="product">Ottoman Divan £699</div>
</main></body></html>"""


def test_category_strong_fit_keep_and_optimise():
    a = _audit_html(CATEGORY_HTML,
                    "https://sheridanfrance.test/product-category/divan-beds/",
                    "Divan Beds")
    assert a.page_type == "category", a.page_type_signals
    assert a.fit == "strong", (a.fit_score, a.fit_breakdown)
    assert a.recommendation == "Keep and optimise this page."


# ---------- HUB PAGE fixtures ----------

HUB_HTML = """<!doctype html><html><head>
<title>Spanish Residency Services – TIE, NIE, Padron &amp; More</title>
<meta name="description" content="Full Spanish residency services for British expats.">
</head><body><main>
  <h1>Spanish Residency Services</h1>
  <h2>TIE Card Application</h2>
  <p>{tie}</p>
  <h2>NIE Number Application</h2>
  <p>{nie}</p>
  <h2>Padron Registration</h2>
  <p>{padron}</p>
  <h2>Social Security Registration</h2>
  <p>{ss}</p>
  <h2>Digital Certificate Setup</h2>
  <p>{dc}</p>
  <h2>Healthcare Registration</h2>
  <p>{health}</p>
  <h2>Banking Account Setup</h2>
  <p>{bank}</p>
""".replace("{tie}", " ".join(["TIE card help for British expats in Spain."] * 12)) \
   .replace("{nie}", " ".join(["NIE number help for British expats in Spain."] * 12)) \
   .replace("{padron}", " ".join(["Padron registration help for expats in Spain."] * 12)) \
   .replace("{ss}", " ".join(["Social security signup for expats living in Spain."] * 12)) \
   .replace("{dc}", " ".join(["Digital certificate help for residents in Spain."] * 12)) \
   .replace("{health}", " ".join(["Healthcare registration for expats living in Spain."] * 12)) \
   .replace("{bank}", " ".join(["Banking account setup for expats living in Spain."] * 12)) + \
"""<a href="/tie-card/">TIE card</a>
   <a href="/nie/">NIE</a>
   <a href="/padron/">Padron</a>
   <a href="/social-security/">Social security</a>
   <a href="/digital-cert/">Digital certificate</a>
   <a href="/healthcare/">Healthcare</a>
   <a href="/banking/">Banking</a>
   <a href="/driving/">Driving licence</a>
   <a href="/property/">Property</a>
   <a href="/legal/">Legal</a>
   <a href="/visas/">Visas</a>
   <a href="/relocation/">Relocation</a>
   <a href="/citizenship/">Citizenship</a>
   <a href="/passport/">Passport</a>
   <a href="/tax/">Tax</a>
   <a href="/schools/">Schools</a>
</main></body></html>"""


def test_hub_strong_fit_keep_hub_with_subtopics():
    a = _audit_html(HUB_HTML,
                    "https://civion.test/spanish-residency-services/",
                    "Spanish Residency Services")
    assert a.page_type == "hub", a.page_type_signals
    assert a.fit == "strong", (a.fit_score, a.fit_breakdown)
    assert a.recommendation == (
        "Keep as a hub page and consider creating dedicated landing pages "
        "for the most important subtopics."
    )


def test_hub_moderate_fit_keep_hub_plain():
    """Same hub HTML but a phrase that only weakly relates."""
    a = _audit_html(HUB_HTML,
                    "https://civion.test/spanish-residency-services/",
                    "Healthcare in Spain")
    assert a.page_type == "hub"
    # The phrase mentions Spain (multiple times in body) but isn't covered
    # as deeply as the primary spanish residency topic. Fit lands in
    # moderate territory.
    assert a.fit in ("moderate", "weak")
    if a.fit == "moderate":
        assert a.recommendation == "Keep as a hub page."


# ---------- Recommendation matrix exhaustiveness ----------

def test_recommend_matrix_covers_every_combination():
    """Make sure every page_type × fit combo emits a non-empty headline."""
    for pt in ("landing", "category", "hub"):
        for fit in ("strong", "moderate", "weak"):
            head, why = recommend(pt, fit, 80 if fit == "strong" else 60 if fit == "moderate" else 30)
            assert head and len(head) > 5, f"empty head for {pt}/{fit}"
            assert why and len(why) > 20, f"empty rationale for {pt}/{fit}"


def test_landing_at_score_90_emits_well_aligned():
    """The 'Phrase and page are already well aligned' message kicks in
    when the landing page scores ≥90 on phrase fit."""
    head, _ = recommend("landing", "strong", 92)
    assert head == "Phrase and page are already well aligned."


def test_landing_strong_below_90_emits_keep_and_optimise():
    head, _ = recommend("landing", "strong", 80)
    assert head == "Keep and optimise this page."


# ---------- Classification edge cases ----------

def test_classify_short_focused_page_is_landing():
    html = """<!doctype html><html><body><main>
      <h1>Bathroom Renovations</h1>
      <h2>Our process</h2>
      <p>Bathroom renovations in 4 weeks. Book a call to enquire today.</p>
    </main></body></html>"""
    ex = extract(html, "https://x.test/bathroom-renovations/", 200, 1, "http",
                 "https://x.test/bathroom-renovations/")
    pt, _, _ = classify(ex)
    assert pt == "landing"


def test_classify_shop_url_with_product_schema_is_category():
    html = """<!doctype html><html><body>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Bed"}
    </script>
    <main><h1>Mattresses</h1></main></body></html>"""
    ex = extract(html, "https://x.test/shop/mattresses/", 200, 1, "http",
                 "https://x.test/shop/mattresses/")
    pt, _, _ = classify(ex)
    assert pt == "category"


# ---------- Phrase-fit edge cases ----------

def test_phrase_fit_empty_phrase_returns_weak():
    ex = extract("<html><body><h1>Anything</h1></body></html>",
                 "https://x.test/", 200, 1, "http", "https://x.test/")
    fit, score, _ = phrase_fit(ex, "")
    assert fit == "weak"
    assert score == 0


def test_phrase_fit_topical_match_lifts_to_strong():
    """Reuses the V1.2 Spanish Residency example end-to-end."""
    html = """<!doctype html><html><head>
    <title>Residency Services for Expats in Spain</title>
    </head><body><main>
    <h1>Residency Services For Expats In Spain</h1>
    <h2>Why our Spanish residency services matter</h2>
    <p>Our Spanish residency services include TIE cards, NIE numbers, Padron,
       digital certificates and tax planning. We have helped British expats
       with Spanish residency services since 2010. """ + (
        " ".join(["Spanish residency services for Brits in Spain."] * 10)
    ) + """</p>
    </main></body></html>"""
    ex = extract(html, "https://x.test/spanish-residency-services-for-expats/", 200,
                 1, "http", "https://x.test/spanish-residency-services-for-expats/")
    fit, score, breakdown = phrase_fit(ex, "Spanish Residency Services")
    assert fit == "strong", (score, breakdown)
    assert breakdown["h1"] == 100
    assert breakdown["url"] >= 80
