"""
Deterministic Target-Phrase Analyser for one live page (V1).

Ten weighted scoring areas. Each atomic check returns (status, priority) so
the UI can group findings into Strengths / Weaknesses / Recommendations
ordered high → low priority.

Weights (sum to 100):
  url               8
  meta_title       15
  meta_description  8
  h1               15
  h2                8
  content          18      <-- NEW: keyword density + topical depth heuristic
  internal_linking  7
  schema           10
  images            6      <-- NEW: alt-text presence + phrase coverage
  faq               5      <-- NEW: FAQ block + JSON-LD FAQPage
"""
from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlparse

from .models import AuditResult, ExtractedPage, ScoreCheck


_PUNCT = re.compile(r"[\s\-_/]+")
_STOPS = {"the", "a", "an", "of", "in", "on", "for", "to", "and", "or"}


def _norm(s: str) -> str:
    return _PUNCT.sub(" ", (s or "").lower()).strip()


def _toks(s: str) -> List[str]:
    return [t for t in _norm(s).split(" ") if t and t not in _STOPS]


def _contains(hay: str, p: str) -> bool:
    return bool(hay and p) and _norm(p) in _norm(hay)


def _at_start(hay: str, p: str, win: int = 60) -> bool:
    return bool(hay and p) and _norm(p) in _norm(hay)[:win]


def _exact(a: str, b: str) -> bool:
    return bool(a) and bool(b) and _norm(a) == _norm(b)


def _partial_overlap(hay: str, p: str) -> float:
    pt = _toks(p)
    if not pt:
        return 0.0
    hs = set(_toks(hay))
    return sum(1 for t in pt if t in hs) / len(pt)


# ---------- areas (each returns (score 0-100, [ScoreCheck])) ----------

def _slug(url: str) -> str:
    path = urlparse(url).path or "/"
    return path.rstrip("/").rsplit("/", 1)[-1] if path != "/" else ""


def s_url(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    is_home = (urlparse(p.url).path or "/") == "/"
    if is_home:
        out.append(ScoreCheck(key="url_home", label="URL is the homepage", area="url",
                              status="pass", priority="low",
                              detail="Homepage URLs are not expected to carry the target phrase."))
        return (100, out)
    slug = _slug(p.url)
    if _exact(slug, phrase):
        out.append(ScoreCheck(key="url_exact", label="URL slug is an exact match for the phrase",
                              area="url", status="pass", priority="high", detail=f"Slug = '{slug}'."))
        return (100, out)
    if _contains(p.url, phrase):
        out.append(ScoreCheck(key="url_contains", label="Phrase is present in the URL",
                              area="url", status="pass", priority="high",
                              detail=f"'{phrase}' is in the URL."))
        return (80, out)
    if _partial_overlap(slug, phrase) >= 0.5:
        out.append(ScoreCheck(key="url_partial", label="URL only partially matches the phrase",
                              area="url", status="warn", priority="medium",
                              detail=f"URL slug contains some tokens of '{phrase}'."))
        return (50, out)
    out.append(ScoreCheck(key="url_missing", label="Phrase missing from the URL",
                          area="url", status="fail", priority="medium",
                          detail=f"'{phrase}' does not appear in the URL slug. "
                                 "Changing established URLs is risky — treat as low-priority unless the page is new."))
    return (10, out)


def s_title(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    t = p.title
    if not t:
        out.append(ScoreCheck(key="title_missing", label="Meta title is missing",
                              area="meta_title", status="fail", priority="high",
                              detail="Set a meta title that contains the primary phrase near the start."))
        return (0, out)
    score = 0
    if _at_start(t, phrase, 30):
        score += 80
        out.append(ScoreCheck(key="title_start", label="Phrase appears at the start of the meta title",
                              area="meta_title", status="pass", priority="high",
                              detail=f"'{phrase}' is in the first 30 chars."))
    elif _contains(t, phrase):
        score += 55
        out.append(ScoreCheck(key="title_present", label="Phrase present in meta title",
                              area="meta_title", status="warn", priority="high",
                              detail=f"'{phrase}' is in the title but not at the start. Move it forward."))
    else:
        out.append(ScoreCheck(key="title_missing_phrase", label="Phrase missing from meta title",
                              area="meta_title", status="fail", priority="high",
                              detail=f"Add '{phrase}' to the meta title, ideally at the start."))
    n = len(t)
    if 50 <= n <= 65:
        score += 20
        out.append(ScoreCheck(key="title_len_ok", label="Meta title length is in range",
                              area="meta_title", status="pass", priority="low",
                              detail=f"{n} chars (recommended 50-65)."))
    elif n < 30:
        out.append(ScoreCheck(key="title_short", label="Meta title is too short",
                              area="meta_title", status="warn", priority="medium",
                              detail=f"Only {n} chars; aim for 50-65."))
    elif n > 65:
        out.append(ScoreCheck(key="title_long", label="Meta title is too long",
                              area="meta_title", status="warn", priority="medium",
                              detail=f"{n} chars; Google often truncates above 65."))
    return (min(score, 100), out)


def s_desc(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    d = p.meta_description
    if not d:
        out.append(ScoreCheck(key="desc_missing", label="Meta description is missing",
                              area="meta_description", status="fail", priority="high",
                              detail="Add a meta description (120-158 chars) including the primary phrase."))
        return (0, out)
    score = 30
    if _contains(d, phrase):
        score += 50
        out.append(ScoreCheck(key="desc_present", label="Phrase present in meta description",
                              area="meta_description", status="pass", priority="medium",
                              detail=f"'{phrase}' is in the meta description."))
    else:
        out.append(ScoreCheck(key="desc_missing_phrase", label="Phrase missing from meta description",
                              area="meta_description", status="fail", priority="high",
                              detail=f"Add '{phrase}' to the meta description."))
    n = len(d)
    if 120 <= n <= 158:
        score += 20
        out.append(ScoreCheck(key="desc_len_ok", label="Meta description length is in range",
                              area="meta_description", status="pass", priority="low",
                              detail=f"{n} chars (recommended 120-158)."))
    elif n < 80:
        out.append(ScoreCheck(key="desc_short", label="Meta description is too short",
                              area="meta_description", status="warn", priority="medium",
                              detail=f"Only {n} chars; expand to 120-158."))
    elif n > 170:
        out.append(ScoreCheck(key="desc_long", label="Meta description is too long",
                              area="meta_description", status="warn", priority="low",
                              detail=f"{n} chars; trim to 120-158."))
    return (min(score, 100), out)


def s_h1(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    if not p.h1:
        out.append(ScoreCheck(key="h1_missing", label="H1 is missing",
                              area="h1", status="fail", priority="high",
                              detail="Add an H1 that contains the primary phrase."))
        return (0, out)
    if len(p.h1) > 1:
        out.append(ScoreCheck(key="h1_multiple", label="Page has multiple H1 tags",
                              area="h1", status="warn", priority="medium",
                              detail=f"Found {len(p.h1)} H1s — pages should have exactly one."))
    h1 = p.h1[0]
    if _exact(h1, phrase):
        out.append(ScoreCheck(key="h1_exact", label="H1 is an exact match for the phrase",
                              area="h1", status="pass", priority="high",
                              detail=f"H1 = '{h1}'."))
        return (100, out)
    if _contains(h1, phrase):
        out.append(ScoreCheck(key="h1_contains", label="H1 contains the phrase",
                              area="h1", status="pass", priority="high",
                              detail=f"H1 '{h1}' contains '{phrase}'."))
        return (85, out)
    if _partial_overlap(h1, phrase) >= 0.6:
        out.append(ScoreCheck(key="h1_partial", label="H1 partially matches the phrase",
                              area="h1", status="warn", priority="high",
                              detail=f"H1 '{h1}' shares tokens with '{phrase}' but is not a substring match."))
        return (55, out)
    out.append(ScoreCheck(key="h1_unrelated", label="H1 does not reference the phrase",
                          area="h1", status="fail", priority="high",
                          detail=f"Rewrite the H1 to include '{phrase}'."))
    return (15, out)


def s_h2(p: ExtractedPage, phrase: str, secondaries: List[str]) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    if not p.h2:
        out.append(ScoreCheck(key="h2_none", label="Page has no H2 subheadings",
                              area="h2", status="warn", priority="medium",
                              detail="Break the page into H2 sections to improve scannability and topic coverage."))
        return (20, out)
    score = 30
    if any(_contains(h, phrase) for h in p.h2):
        score += 40
        out.append(ScoreCheck(key="h2_phrase", label="An H2 references the primary phrase",
                              area="h2", status="pass", priority="medium",
                              detail="At least one H2 contains the primary phrase."))
    else:
        out.append(ScoreCheck(key="h2_no_phrase", label="No H2 references the primary phrase",
                              area="h2", status="warn", priority="medium",
                              detail=f"Add an H2 that contains '{phrase}' or a close variant."))
    if secondaries:
        sec_hits = sum(1 for s in secondaries if any(_contains(h, s) for h in p.h2))
        if sec_hits >= max(1, len(secondaries) // 2):
            score += 30
            out.append(ScoreCheck(key="h2_secondaries", label="H2s cover the secondary phrases",
                                  area="h2", status="pass", priority="low",
                                  detail=f"{sec_hits} of {len(secondaries)} secondary phrases appear in H2s."))
        else:
            out.append(ScoreCheck(key="h2_secondaries_missing", label="Secondary phrases under-covered in H2s",
                                  area="h2", status="warn", priority="medium",
                                  detail=f"Only {sec_hits} of {len(secondaries)} secondary phrases appear in H2s."))
    else:
        score += 30
    return (min(score, 100), out)


def s_content(p: ExtractedPage, phrase: str, secondaries: List[str]) -> Tuple[int, List[ScoreCheck]]:
    """Keyword density (1.0-2.5% sweet spot) + content-depth heuristic."""
    out: List[ScoreCheck] = []
    body = _norm(p.body_text)
    wc = p.word_count
    if wc < 100:
        out.append(ScoreCheck(key="content_thin", label="Page content is thin",
                              area="content", status="fail", priority="high",
                              detail=f"Only {wc} words. Aim for ≥ 600 for a service / target page."))
        return (15, out)

    # Keyword density.
    n_phrase = body.count(_norm(phrase)) if phrase else 0
    density = (n_phrase * len(_toks(phrase)) / wc * 100) if wc else 0.0
    score = 0
    if n_phrase == 0:
        out.append(ScoreCheck(key="content_phrase_missing", label="Primary phrase not found in body content",
                              area="content", status="fail", priority="high",
                              detail=f"Use '{phrase}' at least 2-3 times naturally in the body copy."))
    elif n_phrase < 2:
        score += 25
        out.append(ScoreCheck(key="content_phrase_thin", label="Primary phrase used only once",
                              area="content", status="warn", priority="medium",
                              detail=f"Add 1-2 more natural mentions of '{phrase}' across the page."))
    elif 1.0 <= density <= 2.5:
        score += 55
        out.append(ScoreCheck(key="content_density_ok", label="Keyword density in the optimal range",
                              area="content", status="pass", priority="medium",
                              detail=f"Phrase density {density:.2f}% (sweet spot 1.0-2.5%)."))
    elif density > 4.0:
        score += 25
        out.append(ScoreCheck(key="content_overused", label="Keyword density looks over-optimised",
                              area="content", status="warn", priority="medium",
                              detail=f"Density {density:.2f}% — reduce repetitions to stay below 2.5%."))
    else:
        score += 40
        out.append(ScoreCheck(key="content_density_low", label="Keyword density is below the sweet spot",
                              area="content", status="warn", priority="low",
                              detail=f"Density {density:.2f}%. Aim for 1.0-2.5%."))

    # Depth — secondaries covered in body + word count.
    if secondaries:
        cov = sum(1 for s in secondaries if _contains(body, s))
        if cov >= max(1, len(secondaries) // 2):
            score += 25
            out.append(ScoreCheck(key="content_secondaries", label="Body covers the secondary phrases",
                                  area="content", status="pass", priority="low",
                                  detail=f"{cov} of {len(secondaries)} secondary phrases appear in the body."))
        else:
            out.append(ScoreCheck(key="content_secondaries_missing", label="Secondary phrases under-covered in body",
                                  area="content", status="warn", priority="medium",
                                  detail=f"Only {cov} of {len(secondaries)} secondary phrases appear in the body."))
    else:
        score += 15

    # Depth bonus by word count.
    if wc >= 1500:
        score += 20
        out.append(ScoreCheck(key="content_depth_strong", label="Content depth is strong",
                              area="content", status="pass", priority="low",
                              detail=f"{wc} words — strong depth for a primary target page."))
    elif wc >= 600:
        score += 10
        out.append(ScoreCheck(key="content_depth_ok", label="Content depth is acceptable",
                              area="content", status="pass", priority="low",
                              detail=f"{wc} words — fine, but consider expanding to ≥ 1500 for competitive phrases."))
    else:
        out.append(ScoreCheck(key="content_depth_thin", label="Content depth is light",
                              area="content", status="warn", priority="medium",
                              detail=f"{wc} words — expand to 600+ for a service / target page."))
    return (min(score, 100), out)


def s_internal(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    n = len(p.internal_links)
    score = 0
    if n >= 8:
        score += 60
        out.append(ScoreCheck(key="links_count_strong", label="Strong internal linking presence",
                              area="internal_linking", status="pass", priority="medium",
                              detail=f"{n} internal links from this page."))
    elif n >= 3:
        score += 40
        out.append(ScoreCheck(key="links_count_ok", label="Moderate internal linking",
                              area="internal_linking", status="warn", priority="medium",
                              detail=f"{n} internal links — aim for ≥ 8 contextual links."))
    else:
        out.append(ScoreCheck(key="links_count_weak", label="Weak internal linking",
                              area="internal_linking", status="fail", priority="high",
                              detail=f"Only {n} internal link(s). Add 5+ contextual outbound links to related pages."))
    if phrase and p.internal_links:
        rel = sum(1 for link in p.internal_links if _contains(link.get("anchor", ""), phrase) or _contains(link.get("href", ""), phrase))
        if rel:
            score += 40
            out.append(ScoreCheck(key="anchor_relevant", label="Anchor text references the phrase",
                                  area="internal_linking", status="pass", priority="medium",
                                  detail=f"{rel} internal anchor(s) reference '{phrase}'."))
        else:
            out.append(ScoreCheck(key="anchor_irrelevant", label="No internal anchors reference the phrase",
                                  area="internal_linking", status="warn", priority="medium",
                                  detail=f"None of the {n} internal links use phrase-relevant anchor text."))
    return (min(score, 100), out)


_ROLE_SCHEMAS = {
    "service":  {"Service", "Product", "Offer"},
    "location": {"LocalBusiness", "Place", "Organization"},
    "article":  {"Article", "BlogPosting", "NewsArticle"},
    "homepage": {"Organization", "WebSite", "WebPage"},
}


def s_schema(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    types = set(p.schema_types or [])
    score = 0
    if types:
        score += 50
        out.append(ScoreCheck(key="schema_present", label="Page has structured data",
                              area="schema", status="pass", priority="medium",
                              detail=f"Schema types: {', '.join(sorted(types))}."))
    else:
        out.append(ScoreCheck(key="schema_missing", label="Page has no structured data",
                              area="schema", status="fail", priority="high",
                              detail="Add JSON-LD schema appropriate to this page's role (Service / LocalBusiness / Article)."))
    if "FAQPage" in types:
        score += 20
        out.append(ScoreCheck(key="schema_faq", label="FAQ schema present",
                              area="schema", status="pass", priority="low",
                              detail="FAQPage JSON-LD detected."))
    if any(s in types for s in ("Organization", "LocalBusiness")):
        score += 10
    return (min(score, 100), out)


def s_images(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    n = len(p.images)
    if n == 0:
        out.append(ScoreCheck(key="images_none", label="Page has no images",
                              area="images", status="warn", priority="medium",
                              detail="Add 1-2 relevant images with descriptive alt text."))
        return (20, out)
    with_alt = sum(1 for i in p.images if (i.get("alt") or "").strip())
    coverage = with_alt / n
    score = int(50 * coverage)
    if coverage >= 0.9:
        out.append(ScoreCheck(key="images_alt_ok", label="Image alt text coverage is strong",
                              area="images", status="pass", priority="low",
                              detail=f"{with_alt} of {n} images have alt text."))
    else:
        out.append(ScoreCheck(key="images_alt_gap", label="Images are missing alt text",
                              area="images", status="warn", priority="medium",
                              detail=f"Only {with_alt} of {n} images have alt text."))
    if phrase:
        rel = sum(1 for i in p.images if _contains(i.get("alt", ""), phrase))
        if rel:
            score += 50
            out.append(ScoreCheck(key="images_alt_phrase", label="An image alt mentions the phrase",
                                  area="images", status="pass", priority="low",
                                  detail=f"{rel} image alt text(s) reference '{phrase}'."))
        else:
            out.append(ScoreCheck(key="images_alt_no_phrase", label="No image alt mentions the phrase",
                                  area="images", status="warn", priority="low",
                                  detail=f"Use '{phrase}' in at least one image's alt text."))
    return (min(score, 100), out)


def s_faq(p: ExtractedPage, phrase: str) -> Tuple[int, List[ScoreCheck]]:
    out: List[ScoreCheck] = []
    has_block = bool(p.faq_blocks)
    has_schema = "FAQPage" in (p.schema_types or [])
    score = 0
    if not has_block and not has_schema:
        out.append(ScoreCheck(key="faq_none", label="Page has no FAQ section",
                              area="faq", status="fail", priority="medium",
                              detail="Adding 3-5 FAQs covering buyer questions can win SERP real estate."))
        return (0, out)
    if has_block:
        score += 60
        out.append(ScoreCheck(key="faq_block", label="FAQ block present on the page",
                              area="faq", status="pass", priority="low",
                              detail=f"{len(p.faq_blocks)} FAQ item(s) detected."))
    if has_schema:
        score += 40
        out.append(ScoreCheck(key="faq_schema", label="FAQPage JSON-LD is in place",
                              area="faq", status="pass", priority="low",
                              detail="FAQPage schema increases the chance of FAQ-rich results in SERPs."))
    elif has_block:
        out.append(ScoreCheck(key="faq_no_schema", label="FAQ block present but FAQPage schema missing",
                              area="faq", status="warn", priority="medium",
                              detail="Wrap the FAQ block in FAQPage JSON-LD to unlock rich results."))
    return (min(score, 100), out)


_WEIGHTS = {
    "url": 8,
    "meta_title": 15,
    "meta_description": 8,
    "h1": 15,
    "h2": 8,
    "content": 18,
    "internal_linking": 7,
    "schema": 10,
    "images": 6,
    "faq": 5,
}


def score_page(extracted: ExtractedPage, phrase: str, secondaries: List[str]) -> AuditResult:
    phrase = (phrase or "").strip()
    secondaries = [s.strip() for s in (secondaries or []) if (s or "").strip()]

    if not phrase:
        # Surface a single missing-phrase guidance check.
        return AuditResult(
            url=extracted.url,
            final_url=extracted.final_url,
            primary_phrase="",
            secondary_phrases=secondaries,
            render_method=extracted.render_method,
            fetch_ms=extracted.fetch_ms,
            fetch_status=extracted.status_code,
            overall_score=0,
            area_scores={},
            strengths=[],
            weaknesses=[],
            recommendations=[ScoreCheck(
                key="phrase_missing", label="No primary phrase supplied",
                area="url", status="fail", priority="high",
                detail="Supply a primary target phrase to enable scoring.",
            )],
            page_snapshot=_snapshot(extracted),
        )

    areas: dict = {}
    checks: List[ScoreCheck] = []
    pipeline = {
        "url":              lambda: s_url(extracted, phrase),
        "meta_title":       lambda: s_title(extracted, phrase),
        "meta_description": lambda: s_desc(extracted, phrase),
        "h1":               lambda: s_h1(extracted, phrase),
        "h2":               lambda: s_h2(extracted, phrase, secondaries),
        "content":          lambda: s_content(extracted, phrase, secondaries),
        "internal_linking": lambda: s_internal(extracted, phrase),
        "schema":           lambda: s_schema(extracted, phrase),
        "images":           lambda: s_images(extracted, phrase),
        "faq":              lambda: s_faq(extracted, phrase),
    }
    for k, fn in pipeline.items():
        sub, c = fn()
        areas[k] = sub
        checks.extend(c)

    overall = round(sum(areas[a] * w for a, w in _WEIGHTS.items()) / sum(_WEIGHTS.values()))
    rank = {"high": 0, "medium": 1, "low": 2}
    strengths = sorted([c for c in checks if c.status == "pass"],
                       key=lambda c: (rank.get(c.priority, 3), c.label))
    weaknesses = sorted([c for c in checks if c.status == "fail"],
                        key=lambda c: (rank.get(c.priority, 3), c.label))
    recommendations = sorted([c for c in checks if c.status in ("fail", "warn")],
                             key=lambda c: (rank.get(c.priority, 3), c.label))

    return AuditResult(
        url=extracted.url,
        final_url=extracted.final_url,
        primary_phrase=phrase,
        secondary_phrases=secondaries,
        render_method=extracted.render_method,
        fetch_ms=extracted.fetch_ms,
        fetch_status=extracted.status_code,
        overall_score=overall,
        area_scores=areas,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        page_snapshot=_snapshot(extracted),
    )


def _snapshot(p: ExtractedPage) -> dict:
    return {
        "title": p.title,
        "meta_description": p.meta_description,
        "canonical": p.canonical,
        "h1": p.h1,
        "h2": p.h2,
        "h3": p.h3,
        "word_count": p.word_count,
        "internal_link_count": len(p.internal_links),
        "external_link_count": len(p.external_links),
        "image_count": len(p.images),
        "image_alt_coverage": (
            sum(1 for i in p.images if (i.get("alt") or "").strip()) / len(p.images)
            if p.images else 0.0
        ),
        "schema_types": p.schema_types,
        "faq_count": len(p.faq_blocks),
    }
