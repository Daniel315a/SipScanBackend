import os
from fastapi import FastAPI
from routes.receipts import router as receipts_router
from routes.metadata import router as metadata_router

from repositories.db import engine, Base, SessionLocal
from repositories.receipt_status_repo import ensure_default_statuses  # <- match filename

# Ensure models are registered before create_all
from repositories.models import Receipt, ReceiptStatus  # noqa: F401

app = FastAPI(title="SIPScan - Backend")

os.makedirs(os.getenv("UPLOAD_DIR", "/app/uploads"), exist_ok=True)

@app.get("/health")
async def health():
    # Simple liveness probe; DB ping is handled elsewhere if needed
    return {"status": "ok"}

app.include_router(receipts_router)
app.include_router(metadata_router)

@app.on_event("startup")
async def on_startup() -> None:
    """Create tables and seed default metadata (dev only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await ensure_default_statuses(session)
