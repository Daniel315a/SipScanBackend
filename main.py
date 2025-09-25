import os
from fastapi import FastAPI, Depends
from routes.receipts import router as receipts_router
from routes.metadata import router as metadata_router
from services.auth_service import validate_token
from services.llm_service import LLMService, render_template

from repositories.db import engine, Base, SessionLocal
from repositories.receipt_status_repo import ensure_default_statuses  # <- match filename

# Ensure models are registered before create_all
from repositories.models import Receipt, ReceiptStatus  # noqa: F401

app = FastAPI(title="SIPScan - Backend")

@app.get("/health")
async def health():
    try:
        ping = render_template("prompts/ping.txt", {"app": "SIPScan"})
        reply = await LLMService().generate(ping)
        return {"status": "ok", "llm_sample": reply[:120]}
    except Exception as e:
        return {"status": "degraded", "error": str(e)[:200]}

app.include_router(receipts_router, dependencies=[Depends(validate_token)])
app.include_router(metadata_router, dependencies=[Depends(validate_token)])

@app.on_event("startup")
async def on_startup() -> None:
    """Create tables and seed default metadata (dev only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await ensure_default_statuses(session)
