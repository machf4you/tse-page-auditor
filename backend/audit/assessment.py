"""
Page Assessment — the primary output of the TSE Page Auditor (V1.3+).

For a given URL + target phrase, answer three questions that an SEO
consultant actually cares about:

  1. What kind of page is this?   → page_type ∈ {landing, category, hub}
  2. Does it fit the phrase?      → fit ∈ {strong, moderate, weak}
  3. What's the next action?      → one of five recommendation sentences

Deterministic — no LLM in V1. Uses the topic-matching engine from V1.2
for phrase fit and a small set of strong structural signals for
page-type classification.

V1.3.1 (2026-01-19) — re-tuned the Landing vs Hub boundary.

A focused landing page (e.g. "Bathroom Renovations", "Local SEO
Services", "NIE & TIE Assistance") routinely has 5+ H2 sections
("Our process", "Pricing", "FAQ", "Reviews") and 15+ internal links.
The previous heuristic mis-classified them as Hub. The new rule:

  - Strip H2s that match a known generic landing-page section
    pattern (FAQ / Pricing / Reviews / Process / About / Contact /
    Why Choose Us / Benefits / Gallery / etc.). These don't count
    either way.
  - An H2 introduces a *sub-topic* only when it contains a
    SUBSTANTIVE token that's not in the H1/phrase anchor and not a
    generic decorator word.
  - Hub iff ≥ 4 H2s introduce sub-topics. Otherwise Landing.

The "Spanish Residency Services" Civion case still classifies as Hub
because its H2s name distinct services (TIE Card, NIE Number, Padron,
Social Security, Digital Certificate, Tax Residency) — all introduce
new substantive tokens. The "Bathroom Renovations" landing now
classifies correctly because "Our Process", "Pricing", "FAQ", "Reviews"
are generic, and a vertical-segmented H2 like "Local SEO Services for
restaurants" still only introduces one new substantive token, well
under the 4-sub-topic Hub threshold.
"""
from __future__ import annotations

import re
from itertools import combinations
from urllib.parse import urlparse

from .models import ExtractedPage, PageAssessment
from .scorer import _contains, _norm, _topic_score, _topic_tokens, _stem


# ----------- Page-type signals -----------

_CATEGORY_URL_HINTS = (
    "/shop/", "/store/", "/products/", "/product/",
    "/product-category/", "/product_cat/",
    "/category/", "/categories/",
    "/collection/", "/collections/",
    "/range/", "/c/",
)
_PRODUCT_SCHEMA = {
    "Product", "ItemList", "CollectionPage",
    "OfferCatalog", "AggregateOffer", "Offer",
}
_PRICE_PAT = re.compile(r"(?:[£$€]|USD|GBP|EUR)\s*\d{2,}", re.I)
_COMMERCIAL_CTA = re.compile(
    r"\b(book\s+now|book\s+a\s+call|get\s+a?\s*quote|contact\s+us|call\s+us\s+now|"
    r"enquire(?:\s+now|\s+today)?|request\s+(?:a\s+)?callback|free\s+consultation|"
    r"start\s+(?:now|today)|apply\s+(?:now|online|today)|buy\s+now|"
    r"add\s+to\s+(?:basket|cart|bag)|shop\s+now)\b",
    re.I,
)

# Generic H2 section headings that appear on landing pages without
# introducing a new sub-topic. Matched after stripping trailing punctuation.
_GENERIC_H2_PAT = re.compile(
    r"^("
    r"(?:our|the)\s+(?:process|approach|service|services|story|team|guarantee|"
    r"  values|work|method|methodology|workflow|journey|history|mission|promise)|"
    r"how\s+(?:it\s+|we\s+)?works?|how\s+we\s+(?:work|deliver|operate|help|do\s+it)|"
    r"why\s+(?:choose|work\s+with|hire)\s+us|why\s+us|why\s+(?:choose|hire)|"
    r"what\s+(?:we\s+do|to\s+expect|you\s+(?:get|need))|"
    r"what\s+(?:our|my)\s+clients?\s+(?:say|think)|what\s+people\s+(?:say|think)|"
    r"(?:the\s+)?(?:benefits?|features?|advantages?|results?|outcomes?)|"
    r"(?:pricing|prices|cost|costs|fees|packages?|plans?|investment)"
    r"(?:\s*(?:&|and|\+|/|,|·)\s*(?:pricing|prices|cost|costs|fees|packages?|plans?|investment))*|"
    r"reviews?|testimonials?|client\s+(?:stories|reviews|feedback)|"
    r"faqs?|frequently\s+asked\s+questions|questions?\s+(?:and\s+)?answers?|q\s*&\s*a|"
    r"contact(?:\s+us)?|get\s+in\s+touch|where\s+to\s+find|location|opening\s+hours|"
    r"about(?:\s+us)?|who\s+we\s+are|about\s+the\s+(?:company|team|business)|meet\s+the\s+team|"
    r"book(?:\s+(?:now|a\s+call|a\s+consultation|today))?|"
    r"enquir(?:e|y|ies)(?:\s+(?:now|today))?|"
    r"request\s+(?:a\s+)?(?:quote|callback|call)|free\s+consultation|"
    r"next\s+steps|ready\s+to\s+(?:get\s+)?start(?:ed)?|get\s+started|"
    r"gallery|portfolio|case\s+stud(?:y|ies)|examples?|our\s+work|recent\s+(?:projects?|work)|"
    r"news|blog|articles|latest|related\s+(?:articles?|posts?|reading)|"
    r"on\s+this\s+page|table\s+of\s+contents|contents?|index|summary|overview|introduction|"
    r"trusted\s+by|brands?\s+(?:we|that)\s+(?:trust|work\s+with)|as\s+seen\s+(?:in|on)|"
    r"awards?|certifications?|accreditations?|"
    r"social\s+(?:media|proof)|follow\s+us"
    r")$",
    re.I | re.X,
)

# Words that look substantive in isolation but don't actually introduce a
# new SEO sub-topic. We strip these from H2 tokens before deciding whether
# the H2 is a sub-topic. Stored as the *stemmed* form so the comparison
# matches what _topic_tokens produces.
_GENERIC_TOKEN_SOURCES = {
    "process", "service", "team", "pricing", "price", "cost", "fee", "package",
    "plan", "review", "testimonial", "faq", "contact", "about", "story",
    "approach", "guarantee", "value", "benefit", "feature", "advantage",
    "result", "outcome", "include", "work", "deliver", "operate", "help",
    "page", "site", "website", "section", "way", "tip", "step", "guide",
    "list", "overview", "summary", "introduction", "table", "content",
    "info", "information", "detail", "main", "important", "best", "top",
    "more", "less", "yes", "no", "make", "made", "get", "got", "go",
    "want", "need", "see", "find", "use", "used", "client", "customer",
    "company", "business", "people", "person", "thing", "stuff", "us",
    "we", "you", "they", "them", "ours", "theirs", "near", "around",
    "today", "now", "next", "first", "last", "new", "old",
    "year", "month", "day", "time", "hour", "week",
    "good", "great", "amazing", "perfect", "ideal",
    "matter", "matters", "include", "includes",
    "number", "numbers", "type", "types", "kind", "kinds",
    "starter", "ready", "started",
}
_GENERIC_TOKENS = {_stem(w) for w in _GENERIC_TOKEN_SOURCES}


def _slug_of(url: str) -> str:
    try:
        path = urlparse(url).path
    except Exception:
        path = url or ""
    return path.strip("/").replace("/", " ").replace("-", " ").replace("_", " ").lower()


def _is_generic_h2(h2: str) -> bool:
    text = (h2 or "").strip().rstrip("?.!:")
    return bool(_GENERIC_H2_PAT.match(text))


def _h2_subtopic_tokens(h2: str, anchor_tokens: set) -> set:
    """Substantive tokens in this H2 that aren't already in the anchor and
    aren't generic decorator words. **Two or more** substantive tokens are
    required for the H2 to be treated as a genuine sub-topic — a single
    new noun (e.g. "card" in "What is a TIE card" against
    "NIE & TIE Assistance") is just descriptive language, not a new topic.
    """
    new = _topic_tokens(h2) - anchor_tokens - _GENERIC_TOKENS
    return new if len(new) >= 2 else set()


# ----------- Classification -----------

def classify(page: ExtractedPage, phrase: str = "") -> tuple[str, str, list[str]]:
    """Return (page_type, label, signals_list)."""
    signals: list[str] = []
    url_lower = (page.url or "").lower()

    # 1. CATEGORY — strongest structural signal wins early.
    cat_score = 0
    if any(hint in url_lower for hint in _CATEGORY_URL_HINTS):
        cat_score += 2
        signals.append("URL contains a shop / category / collection path segment")
    matching_schema = [s for s in (page.schema_types or []) if s in _PRODUCT_SCHEMA]
    if matching_schema:
        cat_score += 3
        signals.append(f"Schema.org types include {', '.join(matching_schema)}")
    price_hits = len(_PRICE_PAT.findall(page.body_text or ""))
    if price_hits >= 5:
        cat_score += 2
        signals.append(f"{price_hits} price markers detected in body copy")
    elif price_hits >= 2:
        cat_score += 1
        signals.append(f"{price_hits} price markers in body copy")
    if cat_score >= 3:
        return ("category", "Category Page", signals)

    # 2. LANDING vs HUB — split on whether the page introduces multiple
    #    distinct sub-topics, NOT on H2 count or link breadth.
    h2s = list(page.h2 or [])
    h1 = (page.h1 or [""])[0]
    anchor = h1 or phrase or ""
    anchor_tokens = _topic_tokens(anchor) if anchor else set()

    sub_topic_h2s: list[tuple[str, set]] = []  # (h2_text, new_tokens)
    aligned_h2s: list[str] = []
    generic_h2s: list[str] = []
    for h in h2s:
        if _is_generic_h2(h):
            generic_h2s.append(h)
            continue
        if not anchor_tokens:
            # No anchor to compare against — treat as aligned (don't penalise).
            aligned_h2s.append(h)
            continue
        new_tokens = _h2_subtopic_tokens(h, anchor_tokens)
        if new_tokens:
            sub_topic_h2s.append((h, new_tokens))
        else:
            aligned_h2s.append(h)

    # The single decisive rule: a page is a Hub if ≥4 H2 sections introduce
    # distinct sub-topics. Otherwise it's a Landing — even with many H2s,
    # many internal links and a long word count.
    if len(sub_topic_h2s) >= 4:
        examples = ", ".join(f"'{h}'" for h, _ in sub_topic_h2s[:3])
        signals.append(
            f"{len(sub_topic_h2s)} H2 sections introduce distinct sub-topics "
            f"(e.g. {examples})"
        )
        # H2 pairwise diversity adds colour to the Hub diagnosis when present.
        if len(sub_topic_h2s) >= 4:
            pair_scores = [_topic_score(a, b) for (a, _), (b, _) in
                           combinations(sub_topic_h2s, 2)]
            avg_overlap = (sum(pair_scores) / len(pair_scores)) if pair_scores else 100
            if avg_overlap < 30:
                signals.append(
                    f"Sub-topics are mutually distinct (avg overlap {avg_overlap:.0f}%)"
                )
        if aligned_h2s:
            signals.append(
                f"{len(aligned_h2s)} H2 section(s) still support the H1 topic"
            )
        if generic_h2s:
            signals.append(
                f"{len(generic_h2s)} generic landing-page section(s)"
            )
        return ("hub", "Hub Page", signals)

    # LANDING — surface whichever positive signals we found.
    if aligned_h2s:
        signals.append(
            f"{len(aligned_h2s)} of {len(h2s)} H2 sections support the H1 topic"
        )
    if generic_h2s:
        signals.append(
            f"{len(generic_h2s)} generic landing-page section(s) "
            f"(FAQ / Pricing / Reviews / Process)"
        )
    if sub_topic_h2s:
        signals.append(
            f"{len(sub_topic_h2s)} H2 section(s) touch additional topics but stay "
            f"within the service scope"
        )
    if _COMMERCIAL_CTA.search(page.body_text or ""):
        signals.append("Commercial CTA detected in body copy")
    if (page.word_count or 0) < 1500 and len(h2s) <= 6:
        signals.append("Focused page (under 1500 words, ≤6 H2 sections)")
    return ("landing", "Landing Page", signals)


# ----------- Phrase fit -----------

def phrase_fit(page: ExtractedPage, phrase: str) -> tuple[str, int, dict]:
    """Return (fit, fit_score 0-100, breakdown_dict)."""
    if not phrase:
        return ("weak", 0, {})

    # Title / H1
    title_score = 100 if _contains(page.title, phrase) else _topic_score(phrase, page.title)
    h1 = (page.h1 or [""])[0]
    h1_score = 100 if _contains(h1, phrase) else _topic_score(phrase, h1)

    # URL slug
    slug = _slug_of(page.url)
    url_score = 100 if _contains(slug, phrase) else _topic_score(phrase, slug)

    # H2 — best of the bunch.
    h2_score = 0
    for h in (page.h2 or []):
        if _contains(h, phrase):
            h2_score = 100
            break
        h2_score = max(h2_score, _topic_score(phrase, h))

    # Content — combine exact mention count with topical alignment on a
    # leading slice of the body so we don't reward giant unrelated pages.
    body = page.body_text or ""
    body_norm = _norm(body)
    n_mentions = body_norm.count(_norm(phrase)) if phrase else 0
    if n_mentions >= 3:
        content_score = 100
    elif n_mentions >= 1:
        content_score = 70
    else:
        content_score = min(50, _topic_score(phrase, body[:2000]))

    breakdown = {
        "title": int(title_score),
        "h1": int(h1_score),
        "url": int(url_score),
        "h2": int(h2_score),
        "content": int(content_score),
    }
    weights = {"title": 0.20, "h1": 0.25, "url": 0.15, "h2": 0.15, "content": 0.25}
    fit_score = round(sum(breakdown[k] * w for k, w in weights.items()))

    if fit_score >= 75:
        return ("strong", fit_score, breakdown)
    if fit_score >= 50:
        return ("moderate", fit_score, breakdown)
    return ("weak", fit_score, breakdown)


# ----------- Recommendation matrix -----------

# Decision matrix from the V1.3 spec (page_type × fit → recommendation).
# Five canonical sentences — keep wording stable so the UI / export and any
# future automation can rely on string matching.
_REC_KEEP_OPTIMISE = "Keep and optimise this page."
_REC_KEEP_HUB = (
    "Keep as a hub page and consider creating dedicated landing pages "
    "for the most important subtopics."
)
_REC_KEEP_HUB_PLAIN = "Keep as a hub page."
_REC_IMPROVE_LANDING = "Improve existing landing page."
_REC_BUILD_LANDING = "Create a dedicated landing page for this phrase."
_REC_WELL_ALIGNED = "Phrase and page are already well aligned."


def recommend(page_type: str, fit: str, fit_score: int) -> tuple[str, str]:
    """Return (headline_recommendation, rationale)."""
    if fit == "strong":
        if page_type == "hub":
            return (
                _REC_KEEP_HUB,
                "Hub pages capture broad-topic searches but lose transactional queries "
                "to dedicated landing pages. Keep this as the index page and build "
                "focused landings for the highest-value subtopics.",
            )
        if page_type == "category":
            return (
                _REC_KEEP_OPTIMISE,
                "The category page is well aligned with the target phrase. Focus on "
                "on-page polish (title, copy depth, schema) rather than building a "
                "new page.",
            )
        # landing
        if fit_score >= 90:
            return (
                _REC_WELL_ALIGNED,
                "Title, H1, URL and body all reference the topic. Action the score's "
                "outstanding tweaks rather than restructuring the page.",
            )
        return (
            _REC_KEEP_OPTIMISE,
            "The page targets this phrase clearly. Action the remaining "
            "score-level recommendations to close the gap to 100.",
        )

    if fit == "moderate":
        if page_type == "hub":
            return (
                _REC_KEEP_HUB_PLAIN,
                "The hub is broadly on-topic but the phrase is not strongly featured. "
                "Either tighten the on-page references or build a dedicated landing "
                "page for this specific phrase.",
            )
        return (
            _REC_IMPROVE_LANDING,
            "The page is loosely related to the phrase. Strengthen title, H1, URL "
            "and body alignment before considering a new page.",
        )

    # weak fit
    if page_type == "hub":
        return (
            _REC_BUILD_LANDING,
            "The hub touches this topic only in passing. Keep the hub for "
            "navigation; build a focused landing page that targets the phrase.",
        )
    if page_type == "category":
        return (
            _REC_BUILD_LANDING,
            "This category page doesn't address the target phrase. Either pivot the "
            "category's title and copy, or create a dedicated landing page.",
        )
    return (
        _REC_BUILD_LANDING,
        "The current page is unlikely to rank for the target phrase. A purpose-built "
        "landing page will outperform retrofitting this one.",
    )


# ----------- Public entry point -----------

_LABEL_BY_FIT = {
    "strong": "Strong Fit",
    "moderate": "Moderate Fit",
    "weak": "Weak Fit",
}


def assess(page: ExtractedPage, phrase: str) -> PageAssessment:
    page_type, page_type_label, type_signals = classify(page, phrase)
    fit, fit_score, fit_breakdown = phrase_fit(page, phrase)
    recommendation, rationale = recommend(page_type, fit, fit_score)
    return PageAssessment(
        page_type=page_type,
        page_type_label=page_type_label,
        page_type_signals=type_signals,
        fit=fit,
        fit_label=_LABEL_BY_FIT[fit],
        fit_score=fit_score,
        fit_breakdown=fit_breakdown,
        recommendation=recommendation,
        rationale=rationale,
    )
