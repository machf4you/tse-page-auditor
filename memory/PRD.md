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

### P2 — Phase 2 (Universal Key)
- Semantic phrase-coverage check (LLM-graded relevance)
- Missing-FAQ opportunity discovery
- Trust-signal / topical-authority checks

### P3 — Phase 3
- Competitor-comparison gap analysis (give 2-3 ranking competitor URLs,
  highlight what they have that you don't)

## Personas
- SEO consultant auditing a single client page before recommending edits.
- Marketing manager doing a sanity check before publishing a target page.
- Agency analyst running before/after audits to prove an optimisation worked.
