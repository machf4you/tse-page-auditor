# TSE Page Auditor — V1

## Original problem statement
Build TSE (The Search Equation) Page Auditor V1 from the GitHub repo
`machf4you/tse-page-auditor`. It is a single-page SEO auditor:

> URL + Target Phrase → ANALYSE → 0-100 score + priority-tagged work queue

No ZIP uploads, no site exports, no full-site crawl, no auth. V1 uses
**rule-based / deterministic** checks only (no AI).

## Architecture
- **Backend**: FastAPI + Motor (MongoDB), single `/api` router. Modules:
  - `audit/fetcher.py` — `requests` HTTP fetch (lazy Playwright if `render_js=true`)
  - `audit/extractor.py` — BeautifulSoup → `ExtractedPage`
  - `audit/scorer.py` — 10-area deterministic analyser (sum weights = 100)
  - `audit/models.py` — Pydantic shapes (`AuditRequest`, `AuditResult`, `ScoreCheck`, …)
- **Frontend**: React 19 + react-router-dom 7 + axios. Two pages:
  - `/` — HomePage (form + Recent audits list)
  - `/audits/:auditId` — Result page (score ring, area bars, 3 checklists, page basics)
- **Storage**: Mongo `audits` collection, keyed by `(url, primary_phrase)`.
  Re-runs upsert in place; `id` + `created_at` are immutable via `$setOnInsert`
  so result URLs stay shareable across re-runs. FIFO eviction beyond 100 audits.

## Scoring weights
| Area              | Weight |
|-------------------|-------:|
| URL               |  8%    |
| Meta title        | 15%    |
| Meta description  |  8%    |
| H1                | 15%    |
| H2                |  8%    |
| Content           | 18%    |
| Internal linking  |  7%    |
| Schema            | 10%    |
| Images            |  6%    |
| FAQ               |  5%    |

## API
| Method | Path                 | Body / params                                              | Returns                  |
|--------|----------------------|------------------------------------------------------------|--------------------------|
| GET    | `/api/`              | —                                                          | health                   |
| POST   | `/api/audit`         | `{ url, primary_phrase, secondary_phrases?, render_js? }`  | `AuditResult`            |
| GET    | `/api/audits`        | —                                                          | `[AuditHistoryRow]` ≤100 |
| GET    | `/api/audits/{id}`   | —                                                          | `AuditResult`            |
| DELETE | `/api/audits/{id}`   | —                                                          | `{ deleted: id }`        |

## What's implemented (2026-01-18)
- Imported the full source from `machf4you/tse-page-auditor` into `/app`.
- Backend wired up under `/api` with all 5 endpoints.
- Frontend HomePage + AuditResult pages with all data-testids.
- 6/6 original pytest tests + 13/13 new API integration tests all passing.
- Frontend Playwright pass — 6/6 flows passed.
- Fixed re-run id stability: re-analysing now keeps the original audit id
  (URL stays shareable).

### V1.1 (2026-01-18) — Heading-extraction refinement + Export
- **Heading extraction now scopes to main content.** Layout blocks
  (`<nav>`, `<footer>`, `<aside>`, top-level `<header>`) are stripped
  before `<main>` / `<article>` / `<body>` is picked. Body text and FAQ
  detection use the same cleaned scope.
- **Export Audit Report.** New endpoint
  `GET /api/audits/{id}/export?format=md|txt|pdf`. Markdown for docs,
  plain text for emails, PDF (reportlab) for client deliverables.

### V1.1.1 (2026-01-19) — Layout-strip de-aggression (critical fix)
- **Problem**: V1.1 also class-matched on words like `widget`, `nav`,
  `menu`, `sidebar` etc. WordPress page builders
  (Elementor / Divi / Beaver Builder / Gutenberg) wrap content in
  containers with class names like `elementor-widget` and
  `elementor-element`, so the layout filter silently stripped the
  ENTIRE page content. The Civion residency audit reproduced this
  exactly — H1 found by raw BeautifulSoup but `page_snapshot.h1=[]`,
  `h2=[]`, `word_count=9` in the stored audit.
- **Fix**: dropped the class/id heuristic entirely. Strip only semantic
  HTML5 tags: `<nav>`, `<footer>`, `<aside>`, and the top-level
  `<header>` (site masthead — nested `<header>` inside `<article>` is
  content and stays). The earlier "Sheridan France / Cheap Bed Sale /
  Copyright" noise headings the user reported all sit inside semantic
  layout tags on well-built sites, so semantic-only stripping handles
  them without false positives.
- **Verified**: civion.es now extracts the real H1
  ("Residency Services for Expats in Spain"), 8 H2s, 557 words,
  5 FAQs — score jumps from 41 (bug) to 69 (correct, with V1.2 topic
  match on the H1). New regression test
  `test_wordpress_elementor_widgets_are_not_stripped` locks this in.
- **Markdown / PDF / TXT export contract was already correct** — UI and
  export both read from the same `page_snapshot`. The mismatch reported
  by the user was UI showing what the user *saw* on the page vs. export
  showing what the (broken) extractor stored. With the fix both UI and
  export reflect the real page state.

### V1.3.4 (2026-02) — "Should it become its own page?" sub-topic gate

**User's refined principle**: V1.3.3's sub-topic detector asked "*could*
this H2 become a landing page?", which still over-counted H2s like
"Bathroom Renovation Costs" on a focused service page. The user's
sharper question:

> The distinction is whether the sub-topic **should** become a
> standalone target page.

  - "Bathroom Renovation Costs / Process / FAQs" — facets of the same
    service → reinforce Landing.
  - "TIE Card Application / NIE Number / Padron Registration /
    Social Security Number" — independent services → reinforce Hub.

**Fix**: a new anchor-extension gate runs before the substantive-token
gate. If the H2 contains **all** of the anchor's distinctive tokens
(anchor tokens minus generic decorators), it's a facet of the same
service and does not count, regardless of how many modifier words it
adds. Otherwise the existing ≥2-substantive-new-tokens rule applies.

The signal text now reflects the principle: "Each sub-topic **should
be** its own dedicated landing page rather than a section here" (was
"could reasonably become").

**Tests**: 16 new tests in `tests/test_classification_v134.py` —
includes the user's verbatim Landing facets and Hub independents,
plus the "Public Healthcare System" partial-overlap edge case.
Total backend suite: **129/129 passing**.

### V1.3.2 (2026-01-19) — Landing Precedence gate

**User-reported regression**: V1.3.1 still mis-classified deep landing
pages (*Bathroom Renovations*, *SEO Services*, *Local SEO Services*,
*NIE & TIE Assistance*) as Hub when they had 4+ detailed supporting
sub-sections.

**Fix**: once ≥4 sub-topic H2s are detected, Hub is now **gated** by
three independent signals. A page only becomes a Hub if AT LEAST ONE
gate fails:

  1. **Strong phrase fit** on ≥2 of {title ≥ 80, h1 ≥ 80, url ≥ 50}
  2. **Commercial CTA** present in body copy
  3. **Average ≥150 words per non-generic H2** (depth, not navigation
     cards)

If all three pass → Landing Page (deep landing).
If any fails → Hub Page.

**Verified golden examples**:
- *Bathroom Renovations* / *SEO Services* / *Local SEO Services* /
  *NIE & TIE Assistance* with 5 sub-topic H2s + commercial CTA +
  ≥250 words / H2 → **Landing Page** ✓
- Civion `spanish-residency-services` (live): 7 sub-topic H2s, strong
  fit, but only ~69 words / H2 → fails gate #3 → **Hub Page** ✓
- Synthetic *Healthcare in Spain* / *Education Support* hubs: short
  navigation-card sections + no commercial CTA → **Hub Page** ✓
- Same Bathroom Renovations content but no CTA → fails gate #2 →
  **Hub Page**
- Same content audited against an unrelated phrase → fails gate #1 →
  **Hub Page**

**Tests**: 9 new tests in `tests/test_classification_v132.py`
including all four user landing examples + three user hub examples +
the two failure-mode boundary cases. Total backend suite:
**108/108 passing**.

### V1.3.1 (2026-01-19) — Landing vs Hub classifier refinement

**User-reported regression**: focused service landing pages with ≥ 5 H2s
(*Bathroom Renovations*, *Local SEO Services*, *SEO Services*,
*NIE & TIE Assistance*) were mis-classified as Hub because the V1.3
classifier weighted H2 count and internal-link breadth too heavily.

**New rule** (single decisive heuristic):

1. **Strip generic landing-page H2s** before any analysis. The
   `_GENERIC_H2_PAT` regex catches FAQ / Pricing / Reviews / Process /
   About / Contact / Why Choose Us / Benefits / Gallery / Case Studies /
   Book Now / Enquire Today / Next Steps / What Clients Say / News /
   Awards / etc.
2. A non-generic H2 introduces a **sub-topic** only when it contains
   **two or more** substantive tokens that are NOT in the H1 / phrase
   anchor and NOT in the `_GENERIC_TOKENS` decorator set. A single new
   noun (e.g. "card" in "What is a TIE card" against
   "NIE & TIE Assistance") is just descriptive language, not a new
   topic.
3. **Hub iff ≥ 4 H2 sections introduce sub-topics.** Internal-link
   count, word count, and H2 count alone no longer drive the decision.

**Verified**:
- Civion `spanish-residency-services-help-for-expats` → Hub Page,
  Strong Fit 77 / 100. Signals: *"7 H2 sections introduce distinct
  sub-topics (e.g. 'TIE Card Application', 'NIE Number Application',
  'Empadronamiento Registration')"*. Recommendation unchanged.
- Synthetic landings (*Bathroom Renovations*, *Local SEO Services*,
  *SEO Services*, *NIE & TIE Assistance*) all now classify as Landing
  Page — including the trickiest case where the H2s split between NIE
  and TIE because that *is* the service.
- Synthetic hubs (*Healthcare in Spain*, *Education Support*) classify
  as Hub Page.

**Tests**: 39 new tests in `tests/test_classification_v131.py` covering
the user's golden examples in both directions + the generic-H2 regex
parametrically. Total backend suite: **99/99 passing**.

### V1.3 (2026-01-19) — Page Assessment (primary output)

**Pivot from scoring to decision-making.** Every audit now leads with a
Page Assessment block that answers three questions an SEO consultant
actually cares about:

  1. **Page type** — Landing Page · Category Page · Hub Page
  2. **Target phrase fit** — Strong · Moderate · Weak (0-100 score)
  3. **Strategic recommendation** — one of 5 canonical sentences

The score is still computed and visible (top-right of result page), but
is now secondary. The assessment is what shows first and is what gets
exported.

#### New modules
- `audit/assessment.py` — `classify`, `phrase_fit`, `recommend`, `assess`.
- `PageAssessment` Pydantic model on `AuditResult.page_assessment`.

#### Classification heuristics (deterministic, no LLM)
- **Category**: URL contains `/shop/ /store/ /products/ /category/
  /collection/ /range/ /c/`, JSON-LD includes `Product / CollectionPage /
  ItemList / OfferCatalog / Offer`, ≥ 5 price markers in body. Score ≥ 3
  = category.
- **Hub**: ≥ 5 H2 sections, H2 topical diversity (avg pairwise topic
  overlap < 40 %), ≥ 15 internal links, long content (≥ 800 words)
  without a strong commercial CTA. Score ≥ 3 = hub.
- **Landing** (default): focused page, few H2s, commercial CTA present.

#### Phrase fit (0-100, weighted)
- title 20 %, h1 25 %, url 15 %, h2 15 %, content 25 %.
- Each component uses exact-substring OR the V1.2 `_topic_score`
  fallback, so "Spanish Residency Services" vs "Residency Services For
  Expats In Spain" still scores 100 on title/H1/URL.
- Content score caps at 50 when there is no exact mention — prevents a
  large unrelated page from gaming the fit on topical noise alone.
- Thresholds: ≥75 strong, ≥50 moderate, <50 weak.

#### Recommendation matrix (5 canonical strings, exact-match stable)

| Page type | Strong fit | Moderate fit | Weak fit |
|---|---|---|---|
| Landing | "Keep and optimise this page." (or "Phrase and page are already well aligned." when fit ≥ 90) | "Improve existing landing page." | "Create a dedicated landing page for this phrase." |
| Category | "Keep and optimise this page." | "Improve existing landing page." | "Create a dedicated landing page for this phrase." |
| Hub | "Keep as a hub page and consider creating dedicated landing pages for the most important subtopics." | "Keep as a hub page." | "Create a dedicated landing page for this phrase." |

#### Verified
- **Civion golden case**: page_type = hub, fit = strong (77 / 100),
  recommendation = "Keep as a hub page and consider creating dedicated
  landing pages for the most important subtopics." — matches the user's
  Example 2 verbatim.
- **example.com**: page_type = landing, fit = moderate (62 / 100),
  recommendation = "Improve existing landing page."

#### Tests
- 12 new tests in `tests/test_page_assessment.py` covering each cell of
  the recommendation matrix + classification edge cases + phrase-fit
  edge cases.
- Full backend suite: **60/60 passing**.
- Frontend Playwright pass: assessment renders above area scores,
  testids all present, no regressions on Re-analyse / Export.

#### UI / Export
- Prominent assessment card at the top of `/audits/:id`
  (data-testids: `page-assessment`, `assessment-page-type`,
  `assessment-fit`, `assessment-recommendation`, `assessment-signals`,
  `assessment-fit-breakdown`). Left-accent border, large headline
  recommendation, rationale paragraph, two-column grid for page-type
  pill + fit pill with supporting signal bullets.
- `render_markdown` / `render_text` / `render_pdf` all surface the
  Page Assessment block near the top of every exported report.

### V1.2 (2026-01-18) — Topic Matching
- **Deterministic topic matching** added across URL slug, meta title, H1, H2,
  body content, and image alt text. No LLM (V1 stays AI-free).
- New helpers in `audit/scorer.py`:
  - `_stem(token)` — strips common English suffixes (`ations`, `ation`,
    `tions`, `tion`, `ings`, `ies`, `ing`, `ers`, `er`, `ed`, `es`, `ly`,
    `s`, `y`) and collapses doubled consonants. Tiny + deterministic.
  - `_GEO_NORMALISE` — adjective ↔ country (spanish↔spain, british↔britain,
    french↔france, etc., ~25 entries). Phase 2 LLM will own the long tail.
  - `_topic_tokens(s)` — produces the canonical "topic shape" token set.
  - `_topic_score(target, candidate)` — 0-100 token-cover percentage,
    order-independent.
  - `_topic_match(target, candidate)` — convenience wrapper, threshold 80%.
- New PASS tier inserted between substring-contains and the partial fallback:
  - `url_topic` (area score 75, priority medium, status pass)
  - `title_topic` (warn medium — still suggests leading with the exact phrase)
  - `h1_topic` (area score 80, priority high, status pass)
  - `h2_topic` (counts toward H2 area score 60+)
  - `images_alt_phrase` now accepts topical matches too
  - Body content: keyword density counts exact mentions + topical-equivalent
    sentence-level mentions (split on `.`/`!`/`?`); secondary coverage uses
    topic match as fallback to substring.
- 11 new tests in `tests/test_topic_matching.py` including the user's exact
  example: target `Spanish Residency Services` against H1 `Residency Services
  For Expats In Spain` → 100% topic score → promoted to strength `h1_topic`,
  area score ≥ 80 (was previously a partial-warn at 55).
- Total backend test suite: **40/40 passing**, zero regressions on existing
  fixtures (well-optimised + poor + heading-extraction + export contract).

## Prioritised backlog
### P1 — Quality
- Add an error state to Recent audits when `/api/audits` fails (currently silent).
- Re-validate empty-form handling: HomePage uses HTML5 `required` so the
  React-level `form-error` alert is unreachable. Either drop `required` or
  remove the dead setError branch.

### P2 — Phase 2 (Universal Key) — long-tail semantics

V1.2 already ships **deterministic** topic matching (stem + demonym + token
overlap) so the basic Spanish-Residency case is covered without an LLM. Phase
2 layers in LLM-graded relevance for the long tail that hand-coded rules
can't reach:

- Synonyms and industry jargon that aren't pure morphology
  ("law firm" ↔ "legal practice", "GP" ↔ "general practitioner")
- Tense / aspect drift ("we help you move" ↔ "moving help")
- Cross-lingual demonyms not in `_GEO_NORMALISE`
- Caching grade verdicts on `(target_phrase, candidate_text)` so re-audits
  are free

Plus the original Phase 2 items:

- Missing-FAQ opportunity discovery
- Trust-signal / topical-authority checks

### P2 — Hub Page Detection (new — 2026-01-18)

User insight from the Civion Residency audit: some pages are **hubs** not
landing pages, and the auditor's current "add more phrase mentions"
recommendation is wrong for them.

Hub example:

```
Primary topic:    Spanish Residency Services
Supporting topics:
  - TIE Card Application
  - NIE Number Application
  - Padron Registration
  - Social Security Number
  - Digital Certificates
```

Future scorer should classify each audited page as:

1. **Landing page** — single focused service, current scoring rules apply
2. **Hub page** — broad topic page that links to many supporting pages;
   reward presence of supporting-topic internal links + H2/H3 coverage,
   relax the keyword-density rule, and stop nagging for more exact-phrase
   mentions
3. **Supporting page** — narrow sub-topic of a hub; reward back-link to the
   hub and clear topical alignment

Classification heuristics to explore:
- Internal-link fan-out + diversity of anchor topics → hub signal
- Word count + topic-coverage breadth vs depth → hub vs landing
- Optional LLM judgement when the heuristic is borderline

### P3 — Phase 3
- Competitor-comparison gap analysis (give 2-3 ranking competitor URLs,
  highlight what they have that you don't)

## Personas
- SEO consultant auditing a single client page before recommending edits.
- Marketing manager doing a sanity check before publishing a target page.
- Agency analyst running before/after audits to prove an optimisation worked.
