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

## Prioritised backlog
### P1 — Quality
- Add an error state to Recent audits when `/api/audits` fails (currently silent).
- Re-validate empty-form handling: HomePage uses HTML5 `required` so the
  React-level `form-error` alert is unreachable. Either drop `required` or
  remove the dead setError branch.

### P2 — Phase 2 (Universal Key) — move from phrase matching to **topic matching**

**Problem surfaced in real audits (2026-01-18):** V1 is too literal. It rewards
substring matches and penalises semantically equivalent rewrites. A human SEO
would mark these as strong matches; the current scorer marks them as partial.

| Target phrase                | Page H1 / heading                              | Human verdict | V1 verdict |
|------------------------------|------------------------------------------------|---------------|------------|
| Spanish Residency Services   | Residency Services For Expats In Spain         | strong match  | partial    |
| Spanish Residency Services   | Spanish Residency Help                         | strong match  | partial    |
| Spanish Residency Services   | Spanish Residency Support                      | strong match  | partial    |

And supporting-topic recognition is missing entirely — these should count as
*the same topic cluster* without being listed as secondary phrases:

- TIE Card Application
- NIE Number Application
- Padrón Registration
- → all members of the broader **Spanish Residency** theme.

**What "topic matching" needs to add to the scorer:**
1. **Semantic equivalence** of the primary phrase against title / H1 / H2 / URL
   slug. Use the Universal Key (Claude / Gemini / GPT) to grade equivalence
   on a 0-100 scale rather than substring-only. Cache the verdict on
   `(primary_phrase, candidate_text)` so re-audits are free.
2. **Topical-cluster expansion** of the primary phrase into an LLM-generated
   list of supporting subtopics, then run the existing H2 / body / internal-link
   coverage checks against the expanded cluster instead of only against the
   user-supplied secondary phrases. Surface "supporting topics covered:
   3 of 7" in the area_scores breakdown.
3. **Replace** `_exact / _contains / _partial_overlap` literal helpers in
   `scorer.py` with a `phrase_topic_score(target, candidate) -> int` that
   falls back to literal matching if the LLM call fails, so the engine
   stays deterministic when the key budget is exhausted.
4. Re-tag findings: a heading that's a topical match should land in
   **Strengths**, not as a "partial match" warning in Recommendations.

**Why this matters:** the current scoring is silently nudging users towards
keyword stuffing ("just put the exact phrase in the H1") instead of writing
naturally for a topic. Phase 2 should reverse that incentive.

- Semantic phrase-coverage check (LLM-graded relevance) — covers items 1 & 3 above
- Topical-cluster expansion — item 2 above
- Missing-FAQ opportunity discovery
- Trust-signal / topical-authority checks

### P3 — Phase 3
- Competitor-comparison gap analysis (give 2-3 ranking competitor URLs,
  highlight what they have that you don't)

## Personas
- SEO consultant auditing a single client page before recommending edits.
- Marketing manager doing a sanity check before publishing a target page.
- Agency analyst running before/after audits to prove an optimisation worked.
