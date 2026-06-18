"""
Pydantic models for TSE Page Auditor V1.

Two collections:
  - `audits` — one document per audit run (max 100, FIFO eviction).
              Keyed by (url, primary_phrase). A second run on the same
              pair overwrites the previous entry so re-analysing after a
              fix gives a delta rather than piling up.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


Priority = Literal["high", "medium", "low"]
CheckStatus = Literal["pass", "warn", "fail"]
Area = Literal[
    "url",
    "meta_title",
    "meta_description",
    "h1",
    "h2",
    "content",
    "internal_linking",
    "schema",
    "images",
    "faq",
]


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str
    primary_phrase: str
    secondary_phrases: List[str] = Field(default_factory=list)
    render_js: bool = False


class ExtractedPage(BaseModel):
    """Structured HTML extraction handed to the scorer."""
    model_config = ConfigDict(extra="ignore")

    url: str
    final_url: str = ""
    status_code: int = 0
    fetch_ms: int = 0
    render_method: Literal["http", "js"] = "http"

    title: str = ""
    meta_description: str = ""
    canonical: str = ""
    h1: List[str] = Field(default_factory=list)
    h2: List[str] = Field(default_factory=list)
    h3: List[str] = Field(default_factory=list)
    body_text: str = ""
    word_count: int = 0
    internal_links: List[dict] = Field(default_factory=list)  # [{href, anchor}]
    external_links: List[dict] = Field(default_factory=list)
    schema_types: List[str] = Field(default_factory=list)
    images: List[dict] = Field(default_factory=list)  # [{src, alt}]
    faq_blocks: List[dict] = Field(default_factory=list)  # [{question, answer}]


class ScoreCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    area: Area
    status: CheckStatus
    priority: Priority
    detail: str = ""


class AuditResult(BaseModel):
    """Full audit payload returned to the UI and stored in Mongo."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    final_url: str = ""
    primary_phrase: str
    secondary_phrases: List[str] = Field(default_factory=list)
    render_method: Literal["http", "js"] = "http"
    fetch_ms: int = 0
    fetch_status: int = 0

    overall_score: int = 0
    area_scores: dict = Field(default_factory=dict)
    strengths: List[ScoreCheck] = Field(default_factory=list)
    weaknesses: List[ScoreCheck] = Field(default_factory=list)
    recommendations: List[ScoreCheck] = Field(default_factory=list)

    # Page-basics snapshot so the result page can render without re-fetching.
    page_snapshot: dict = Field(default_factory=dict)

    created_at: str = Field(default_factory=_now_iso)


class AuditHistoryRow(BaseModel):
    """Slim row for the recent-audits list."""
    model_config = ConfigDict(extra="ignore")

    id: str
    url: str
    primary_phrase: str
    overall_score: int
    created_at: str
