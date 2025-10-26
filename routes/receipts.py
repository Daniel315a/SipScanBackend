# routes/receipt.py
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from pydantic import BaseModel, ConfigDict, AnyHttpUrl, field_serializer
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from zoneinfo import ZoneInfo
from datetime import datetime
import asyncio

from repositories.db import get_session, get_sessionmaker
from services import receipt_service
from services import receipt_image_service

_BOGOTA = ZoneInfo("America/Bogota")

router = APIRouter(prefix="/receipts", tags=["receipts"])

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
    url: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None

    @field_serializer("created_at")
    def _to_bogota_img(self, dt: datetime, _info):
        return dt.astimezone(_BOGOTA).isoformat()

@router.post("", response_model=Receipt, status_code=201)
async def create_receipt(
    uploader_nit: str = Form(..., min_length=3, max_length=30),
    images: List[UploadFile] = File(..., description="One or more receipt image files"),
    session: AsyncSession = Depends(get_session),
    session_factory: "async_sessionmaker[AsyncSession]" = Depends(get_sessionmaker),  # 👈 nuevo
):
    """Receive multiple images via multipart and create the receipt."""
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required.")
    if len(images) > 10:
        raise HTTPException(status_code=400, detail="A receipt can have at most 10 images.")

    # Validate all uploaded image types
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

        # Schedule OCR
        asyncio.create_task(
            receipt_image_service.run_ocr_for_receipt(
                session_factory,
                receipt_id=UUID(str(result["id"])),
            )
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{receipt_id}", response_model=Receipt)
async def get_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    rec = await receipt_service.get_receipt(session, receipt_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return Receipt.model_validate(rec)

@router.get("/by-nit/{uploader_nit}", response_model=List[ReceiptRead])
async def list_receipts_by_nit(
    uploader_nit: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List receipts filtered by uploader NIT."""
    recs = await receipt_service.list_by_nit(session, uploader_nit, limit=limit, offset=offset)

    return [ReceiptRead.model_validate(r) for r in recs]

@router.post("/{receipt_id}/suggest", response_model=ReceiptRead)
async def suggest_accounting(
    receipt_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    try:
        rec_dict = await receipt_service.generate_accounting(
            session, app=request.app, receipt_id=receipt_id
        )
        return rec_dict
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Generation failed")

@router.post("/{receipt_id}/accept", response_model=ReceiptRead)
async def accept_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await receipt_service.accept_accounting(session, receipt_id=receipt_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{receipt_id}/reject", response_model=ReceiptRead)
async def reject_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await receipt_service.reject_accounting(session, receipt_id=receipt_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    