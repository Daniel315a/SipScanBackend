import asyncio
import logging
import os

from fastapi import FastAPI, Depends
from routes.receipts import router as receipts_router, ws_router as receipts_ws_router
from routes.metadata import router as metadata_router
from routes.v2.receipts import router as receipts_v2_router
from services.auth_service import validate_token

from sqlalchemy import text
from repositories.db import engine, Base, session_factory
from repositories.receipt_status_repo import ensure_default_statuses
from repositories import receipt_repo

# Ensure models are registered before create_all
from repositories.models import Receipt, ReceiptStatus  # noqa: F401

logger = logging.getLogger(__name__)

WATCHDOG_INTERVAL_SECONDS = 5 * 60  # 15 minutes


async def _stuck_receipt_watchdog():
    """Every 15 min mark receipts stuck in 'extracted_text' as failed."""
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL_SECONDS)
        try:
            async with session_factory() as session:
                count = await receipt_repo.mark_stuck_as_failed(session)
                if count:
                    logger.info("Watchdog: marked %d stuck receipt(s) as failed.", count)
        except Exception:
            logger.exception("Watchdog: error during stuck-receipt sweep.")


app = FastAPI(title="SIPScan - Backend")

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(receipts_router, dependencies=[Depends(validate_token)])
app.include_router(metadata_router, dependencies=[Depends(validate_token)])
app.include_router(receipts_ws_router)
app.include_router(receipts_v2_router, prefix="/v2", dependencies=[Depends(validate_token)])

@app.on_event("startup")
async def on_startup() -> None:
    """Create tables, seed default metadata, and start background watchdog."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await ensure_default_statuses(session)
    asyncio.create_task(_stuck_receipt_watchdog())
