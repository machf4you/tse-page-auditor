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
  (`<nav>`, `<footer>`, `<aside>`, top-level `<header>`, plus class / id
  heuristics for `nav`, `navigation`, `menu`, `sidebar`, `widget`,
  `copyright`, `breadcrumb`, `testimonial`, `masthead`, `site-header`,
  `page-footer`, `footer-area`, `header-area`, `top-bar`) are stripped
  before `<main>` / `<article>` / `<body>` is picked. Body text and FAQ
  detection use the same cleaned scope. 3 tests in
  `tests/test_heading_extraction.py` lock the fixture in.
- **Export Audit Report.** New endpoint
  `GET /api/audits/{id}/export?format=md|txt|pdf`. Markdown for docs,
  plain text for emails, PDF (reportlab) for client deliverables.

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
