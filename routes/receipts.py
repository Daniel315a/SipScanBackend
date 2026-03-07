# routes/receipt.py
import jwt, os
from uuid import UUID
from typing import List

from fastapi import (
    APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request,
    WebSocket, WebSocketDisconnect
)
from pydantic import BaseModel, ConfigDict, AnyHttpUrl, field_serializer
from typing import Any, Literal, Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from zoneinfo import ZoneInfo
from datetime import date, datetime, time
import asyncio

from repositories.db import get_session, get_sessionmaker
from services import receipt_service
from services import receipt_image_service
from repositories import receipt_repo
from repositories import receipt_status_repo

_BOGOTA = ZoneInfo("America/Bogota")

router = APIRouter(prefix="/receipts", tags=["receipts"])

# --- Simple WS connection manager ---
class _WSManager:
    def __init__(self):
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast(self, message: dict):
        to_drop = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                to_drop.append(ws)
        for ws in to_drop:
            self.disconnect(ws)

ws_manager = _WSManager()
ws_router = APIRouter(prefix="/receipts", tags=["receipts-ws"])
SECRET = os.getenv("AUTH_SECRET", "***")

# Restrict accepted content types (extend as needed)
ALLOWED_IMAGE_TYPES: set[str] = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/tiff", "image/heic"
}

class ReceiptImage(BaseModel):
    id: UUID
    img_number: int
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    url: AnyHttpUrl
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at")
    def _to_bogota_img(self, dt: datetime, _info):
        return dt.astimezone(_BOGOTA).isoformat()

class Receipt(BaseModel):
    id: UUID
    uploader_nit: str
    status_id: int
    status: Optional[str] = None
    accounting_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    summary: str
    images: List[ReceiptImage] = []
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at")
    def _to_bogota_img(self, dt: datetime, _info):
        return dt.astimezone(_BOGOTA).isoformat()

class ReceiptStatusRead(BaseModel):
    id: int
    code: str
    label: str
    is_final: bool
    model_config = ConfigDict(from_attributes=True)

class ReceiptRead(BaseModel):
    id: UUID
    created_at: datetime
    status: Optional[ReceiptStatusRead] = None
    summary: str = None
    url: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None

    @field_serializer("created_at")
    def _to_bogota_img(self, dt: datetime, _info):
        return dt.astimezone(_BOGOTA).isoformat()


class PagedReceiptRead(BaseModel):
    items: List[ReceiptRead]
    page_size: int
    next_cursor: Optional[int] = None
    total_estimated: int


@router.post("", response_model=ReceiptRead, status_code=201)
async def create_receipt(
    uploader_nit: str = Form(..., min_length=3, max_length=30),
    images: List[UploadFile] = File(..., description="One or more receipt image files"),
    session: AsyncSession = Depends(get_session),
    session_factory: "async_sessionmaker[AsyncSession]" = Depends(get_sessionmaker),
    request: Request = None,
):
    """Receive multiple images via multipart and create the receipt."""
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required.")
    if len(images) > 10:
        raise HTTPException(status_code=400, detail="A receipt can have at most 10 images.")

    for idx, img in enumerate(images):
        if img.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported media type at index {idx}: {img.content_type}.",
            )

    try:
        result = await receipt_service.create(
            session, uploader_nit=uploader_nit, images=images
        )

        await session.commit()

        receipt_id = UUID(str(result["id"]))

        async def _bg_chain_ocr_then_generate():
            try:
                await receipt_image_service.run_ocr_for_receipt(
                    session_factory,
                    receipt_id=receipt_id,
                )

                async with session_factory() as bg_session:
                    rec = await receipt_repo.get_receipt(bg_session, receipt_id)

                    status_obj = None

                    if getattr(rec, "status", None):
                        status_obj = {
                            "id": rec.status.id,
                            "code": rec.status.code,
                            "label": rec.status.label,
                            "is_final": rec.status.is_final,
                        }

                    await ws_manager.broadcast({
                        "event": "ocr_completed",
                        "receipt_id": str(rec.id),
                        "created_at": rec.created_at.isoformat(),
                        "status": status_obj,
                        "summary": rec.summary,
                    })

                async with session_factory() as bg_session:
                    await receipt_service.generate_accounting(
                        bg_session,
                        app=request.app,
                        receipt_id=receipt_id,
                    )

                    rec2 = await receipt_repo.get_receipt(bg_session, receipt_id)

                    status_obj2 = None
                    if getattr(rec2, "status", None):
                        status_obj2 = {
                            "id": rec2.status.id,
                            "code": rec2.status.code,
                            "label": rec2.status.label,
                            "is_final": rec2.status.is_final,
                        }

                    await ws_manager.broadcast({
                        "event": "suggestion_completed",
                        "receipt_id": str(rec2.id),
                        "created_at": rec2.created_at.isoformat(),
                        "status": status_obj2,
                        "summary": rec2.summary,
                    })
                    
            except Exception as e:
                import logging
                logging.exception("Background OCR→generate task failed: %s", e)

        asyncio.create_task(_bg_chain_ocr_then_generate())

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{receipt_id}", response_model=Receipt)
async def get_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    rec = await receipt_service.get_receipt(session, receipt_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return Receipt.model_validate(rec)

@router.get("/by-nit/{uploader_nit}", response_model=PagedReceiptRead)
async def list_receipts_by_nit(
    uploader_nit: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    summary: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List receipts filtered by uploader NIT with optional date range and summary filters."""
    if to_date and not from_date:
        raise HTTPException(status_code=400, detail="to_date requires from_date.")
    effective_from = datetime.combine(from_date, time.min) if from_date else None
    effective_to = datetime.combine(to_date, time(23, 59, 59)) if to_date else None
    result = await receipt_service.list_by_nit(
        session, uploader_nit,
        limit=limit, offset=offset,
        from_date=effective_from, to_date=effective_to, summary_filter=summary,
    )
    return PagedReceiptRead(
        items=[ReceiptRead.model_validate(r) for r in result["items"]],
        page_size=result["page_size"],
        next_cursor=result["next_cursor"],
        total_estimated=result["total_estimated"],
    )

class ReceiptUpdate(BaseModel):
    status: Literal["accepted", "rejected"]

@router.patch("/{receipt_id}", response_model=ReceiptRead)
async def update_receipt(receipt_id: UUID, body: ReceiptUpdate, session: AsyncSession = Depends(get_session)):
    try:
        if body.status == "accepted":
            return await receipt_service.accept_accounting(session, receipt_id=receipt_id)
        else:
            return await receipt_service.reject_accounting(session, receipt_id=receipt_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@ws_router.websocket("/ws")
async def receipts_ws(websocket: WebSocket):
    
    token = websocket.query_params.get("token")
    if token:
        try:
            jwt.decode(token, SECRET, algorithms=["HS256"])
        except Exception:
            await websocket.close(code=1008, reason="Invalid token")
            return

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)