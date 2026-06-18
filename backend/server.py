"""
TSE Page Auditor V1 — FastAPI entry point.

Endpoints (all under /api):
  GET  /                              health
  POST /audit                         { url, primary_phrase, secondary_phrases?, render_js? } → AuditResult
  GET  /audits                        recent audits list (max 100)
  GET  /audits/{id}                   one full AuditResult
  DELETE /audits/{id}                 remove one audit
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from audit.fetcher import FetchError, fetch
from audit.extractor import extract
from audit.models import AuditHistoryRow, AuditRequest, AuditResult
from audit.scorer import score_page


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="TSE Page Auditor", version="1.0.0")
api = APIRouter(prefix="/api")

MAX_HISTORY = 100


@api.get("/")
async def root():
    return {"app": "TSE Page Auditor", "status": "ok"}


@api.post("/audit", response_model=AuditResult)
async def run_audit(req: AuditRequest):
    if not (req.url or "").strip():
        raise HTTPException(400, "URL is required")
    if not (req.primary_phrase or "").strip():
        raise HTTPException(400, "Primary phrase is required")

    try:
        html, final_url, status, fetch_ms, method = fetch(req.url, render_js=req.render_js)
    except FetchError as exc:
        raise HTTPException(400, str(exc))

    extracted = extract(html, final_url, status, fetch_ms, method, req.url)
    result = score_page(extracted, req.primary_phrase, req.secondary_phrases)

    # Persist (upsert on (url, primary_phrase)) and FIFO-evict beyond MAX_HISTORY.
    doc = result.model_dump()
    await db.audits.update_one(
        {"url": result.url, "primary_phrase": result.primary_phrase},
        {"$set": doc},
        upsert=True,
    )
    # Evict oldest if we're over MAX_HISTORY.
    total = await db.audits.count_documents({})
    if total > MAX_HISTORY:
        excess = total - MAX_HISTORY
        cur = db.audits.find({}, {"_id": 0, "id": 1}).sort("created_at", 1).limit(excess)
        async for old in cur:
            await db.audits.delete_one({"id": old["id"]})

    return result


@api.get("/audits", response_model=List[AuditHistoryRow])
async def list_audits():
    cur = db.audits.find({}, {"_id": 0}).sort("created_at", -1).limit(MAX_HISTORY)
    rows: List[AuditHistoryRow] = []
    async for d in cur:
        rows.append(AuditHistoryRow(
            id=d["id"],
            url=d.get("url", ""),
            primary_phrase=d.get("primary_phrase", ""),
            overall_score=int(d.get("overall_score") or 0),
            created_at=d.get("created_at", ""),
        ))
    return rows


@api.get("/audits/{audit_id}", response_model=AuditResult)
async def get_audit(audit_id: str):
    doc = await db.audits.find_one({"id": audit_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Audit not found")
    return AuditResult(**doc)


@api.delete("/audits/{audit_id}")
async def delete_audit(audit_id: str):
    res = await db.audits.delete_one({"id": audit_id})
    if not res.deleted_count:
        raise HTTPException(404, "Audit not found")
    return {"deleted": audit_id}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
