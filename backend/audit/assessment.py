"""
Page Assessment — the primary output of the TSE Page Auditor (V1.3+).

For a given URL + target phrase, answer three questions that an SEO
consultant actually cares about:

  1. What kind of page is this?   → page_type ∈ {landing, category, hub}
  2. Does it fit the phrase?      → fit ∈ {strong, moderate, weak}
  3. What's the next action?      → one of five recommendation sentences

Deterministic — no LLM in V1. Uses the topic-matching engine from V1.2
for phrase fit and a small set of strong structural signals
(URL hints, JSON-LD schema, H2 count + diversity, internal-link breadth,
commercial CTAs) for page-type classification.
"""
from __future__ import annotations

import re
from itertools import combinations
from urllib.parse import urlparse

from .models import ExtractedPage, PageAssessment
from .scorer import _contains, _norm, _topic_score


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


def _slug_of(url: str) -> str:
    try:
        path = urlparse(url).path
    except Exception:
        path = url or ""
    return path.strip("/").replace("/", " ").replace("-", " ").replace("_", " ").lower()


# ----------- Classification -----------

def classify(page: ExtractedPage) -> tuple[str, str, list[str]]:
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

    # 2. HUB — broad, multi-topic page that mostly navigates to deeper pages.
    hub_signals: list[str] = []
    hub_score = 0
    h2s = list(page.h2 or [])
    if len(h2s) >= 5:
        hub_score += 1
        hub_signals.append(f"{len(h2s)} H2 sections across the page")
    # H2 topical diversity — average pairwise topic overlap; low = diverse.
    if len(h2s) >= 4:
        pair_scores = [_topic_score(a, b) for a, b in combinations(h2s, 2)]
        avg_overlap = (sum(pair_scores) / len(pair_scores)) if pair_scores else 100
        if avg_overlap < 40:
            hub_score += 2
            hub_signals.append(
                f"H2 sections cover diverse subtopics (avg overlap {avg_overlap:.0f}%)"
            )
        elif avg_overlap < 60:
            hub_score += 1
            hub_signals.append(
                f"H2 sections cover several subtopics (avg overlap {avg_overlap:.0f}%)"
            )
    if len(page.internal_links or []) >= 15:
        hub_score += 1
        hub_signals.append(
            f"{len(page.internal_links)} internal links — wide navigation footprint"
        )
    has_cta = bool(_COMMERCIAL_CTA.search(page.body_text or ""))
    if (page.word_count or 0) >= 800 and not has_cta:
        hub_score += 1
        hub_signals.append("Long-form content without a strong commercial CTA")
    if hub_score >= 3:
        return ("hub", "Hub Page", signals + hub_signals)

    # 3. Default — LANDING. Surface whichever positive signals we found.
    signals.extend(hub_signals)
    if has_cta:
        signals.append("Commercial CTA detected in body copy")
    if (page.word_count or 0) < 800 and len(h2s) <= 4:
        signals.append("Focused page (one or two sections, low word count)")
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
    page_type, page_type_label, type_signals = classify(page)
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
